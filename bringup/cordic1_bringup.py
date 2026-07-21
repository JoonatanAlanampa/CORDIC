# SPDX-FileCopyrightText: © 2026 Joonatan Alanampa
# SPDX-License-Identifier: Apache-2.0
"""
CORDIC-1 silicon bring-up — MicroPython for the TinyTapeout demo board RP2040.

Self-checking mirror of the cocotb suite in ../test/test.py, run against the
real die instead of a simulator. Copy this file to the demo board's filesystem
and:

    >>> import cordic1_bringup as bu
    >>> bu.main()             # full self-check, prints a PASS/FAIL table
    >>> bu.demo_scale()       # play a chromatic-ish scale on the Audio Pmod
    >>> bu.sweep_fmax()       # find the die's max working clock

What is actually being proven (all from the pins, no bus on this chip):

  1. heartbeat   uo[0] = bit 23 of a free-running counter -> f = clk / 2**24.
                 Measuring it recovers the clock the die really sees; the whole
                 rest of the script is checked against THAT number, not against
                 the frequency we asked the RP2040 PWM for.
  2. square sync uo[6] = phase[19] of the DDS -> f = inc(code)/2**20 * clk/359.
                 Sweeping ui[6:0] and fitting this over 8 codes exercises the
                 CORDIC schedule, the DDS accumulator and the input pins at once.
  3. level bar   uo[5:1] = sine sample, offset binary. A stuck or rail-parked
                 bar means the engine is not converting even if the DDS ticks.
  4. sigma-delta uo[7] density ~50% over whole periods (best-effort: the RP2040
                 cannot sample a 25 MHz stream, so this is a coarse DC check —
                 the real verdict is a scope/RC filter or the Audio Pmod).

Constants come from src/project.sv; keep them in sync with the RTL.
"""

import time

try:
    from machine import Pin, time_pulse_us
except ImportError:  # pragma: no cover - lets the file be imported on a host
    Pin = None
    time_pulse_us = None

# ---------------------------------------------------------------- design facts
DESIGN = "tt_um_joonatanalanampa_cordic"
CLK_HZ = 25_000_000  # info.yaml clock_hz
OPS_DIV = 359  # constant-time bit-serial conversion, formally proven
BEAT_BIT = 23  # heartbeat = beat[23] -> period 2**24 clocks
PHASE_BITS = 20

BIT_HEARTBEAT = 0
BIT_LEVEL_LSB = 1  # uo[5:1] level bar
BIT_LEVEL_MSB = 5
BIT_SQUARE = 6
BIT_SINE = 7


def dds_inc(code):
    """Phase increment for a frequency code — mirrors src/project.sv."""
    if code == 0:
        return 6625  # 440.0 Hz wake-up tone
    if code == 127:
        return 30  # ~2 Hz breathe mode
    return code << 10


def expected_hz(code, clk_hz):
    return dds_inc(code) / (1 << PHASE_BITS) * (clk_hz / OPS_DIV)


# ------------------------------------------------------- demo-board API shim
# The tt-micropython-firmware API has drifted between releases and the chips
# land ~mid-2027, so every board call goes through a probe here. If a future
# firmware renames something, this is the only section that needs touching.


class Board:
    def __init__(self, tt):
        self.tt = tt

    # -- construction ----------------------------------------------------
    @classmethod
    def open(cls):
        from ttboard.demoboard import DemoBoard

        try:
            tt = DemoBoard.get()  # singleton accessor (newer firmware)
        except AttributeError:
            tt = DemoBoard()
        self = cls(tt)
        self._take_control()
        return self

    def _take_control(self):
        """Drive ui_in from the RP2040 rather than from the DIP switches."""
        try:
            from ttboard.mode import RPMode

            self.tt.mode = RPMode.ASIC_RP_CONTROL
        except Exception as e:  # noqa: BLE001 - firmware variance is expected
            log("note: could not set ASIC_RP_CONTROL (%s);" % e)
            log("      set the input DIP switches by hand if codes do not take")

    # -- design selection -------------------------------------------------
    def select(self, name=DESIGN):
        shuttle = self.tt.shuttle
        proj = getattr(shuttle, name, None)
        if proj is None and hasattr(shuttle, "find"):
            hits = shuttle.find(name)
            proj = hits[0] if hits else None
        if proj is None:
            raise RuntimeError(
                "%s not found on this shuttle — is the firmware's shuttle "
                "index up to date (TTSKY26c)?" % name
            )
        proj.enable()
        return proj

    # -- clock / reset -----------------------------------------------------
    def clock(self, hz):
        self.tt.clock_project_PWM(hz)

    def clock_stop(self):
        try:
            self.tt.clock_project_stop()
        except AttributeError:
            pass

    def reset_pulse(self, settle_ms=5):
        self.tt.reset_project(True)
        time.sleep_ms(settle_ms)
        self.tt.reset_project(False)
        time.sleep_ms(settle_ms)

    # -- pins ---------------------------------------------------------------
    def set_ui(self, value):
        try:
            self.tt.ui_in.value = value
        except AttributeError:
            self.tt.input_byte = value

    def get_uo(self):
        try:
            return int(self.tt.uo_out.value)
        except AttributeError:
            return int(self.tt.output_byte)

    def uo_pin(self, index):
        """A raw machine.Pin for uo[index], or None if it cannot be resolved.

        time_pulse_us() needs a real Pin; without one we fall back to polling
        the output byte, which is accurate enough only for slow signals.
        """
        cand = None
        try:
            cand = self.tt.uo_out[index]
        except Exception:  # noqa: BLE001
            pins = getattr(self.tt, "pins", None)
            if pins is not None:
                cand = getattr(pins, "uo_out%d" % index, None)
        if cand is None:
            return None
        if Pin is not None and isinstance(cand, Pin):
            return cand
        raw = getattr(cand, "raw_pin", None)
        if raw is not None:
            return raw
        return cand if hasattr(cand, "value") else None


# ---------------------------------------------------------------- measurement


def measure_pin_hz(pin, pulses=64, timeout_us=1_000_000):
    """Frequency of a ~square signal by averaging `pulses` half-periods.

    time_pulse_us quantises to 1 us; averaging 64 pulses keeps the error under
    ~0.5% even at the top code (8.6 kHz, 58 us half-period). Returns None if
    the signal never transitions (stuck pin / dead design).
    """
    total = 0
    got = 0
    for level in (1, 0):
        for _ in range(pulses // 2):
            w = time_pulse_us(pin, level, timeout_us)
            if w < 0:
                continue
            total += w
            got += 1
    if got < pulses // 4:
        return None
    return 1e6 / (2.0 * (total / got))


def measure_byte_hz(board, bit, window_ms, settle_ms=0):
    """Frequency of one output bit by polling the whole output byte.

    Slow (a few tens of kHz of samples at best) — used for the ~1.5 Hz
    heartbeat and as the fallback when no raw Pin is available.
    """
    if settle_ms:
        time.sleep_ms(settle_ms)
    mask = 1 << bit
    t0 = time.ticks_us()
    prev = board.get_uo() & mask
    edges = 0
    first = last = None
    while time.ticks_diff(time.ticks_us(), t0) < window_ms * 1000:
        cur = board.get_uo() & mask
        if cur != prev:
            last = time.ticks_us()
            if first is None:
                first = last
            edges += 1
            prev = cur
    # time between the FIRST and LAST edge seen, not the whole window: the
    # window ends mid-period, and at ~1.5 Hz that truncation is a 10% error.
    if edges < 2 or first is None or last == first:
        return None
    span = time.ticks_diff(last, first) / 1e6
    return (edges - 1) / 2.0 / span


def sample_bytes(board, n):
    out = []
    for _ in range(n):
        out.append(board.get_uo())
    return out


# ------------------------------------------------------------------- checks

_results = []


def log(msg):
    print(msg)


def check(name, ok, detail=""):
    _results.append((name, bool(ok), detail))
    log("  [%s] %-26s %s" % ("PASS" if ok else "FAIL", name, detail))
    return ok


def check_close(name, got, want, tol, unit="Hz"):
    if got is None:
        return check(name, False, "no transitions (want %.3f %s)" % (want, unit))
    err = abs(got - want) / want if want else abs(got)
    return check(
        name,
        err < tol,
        "%.3f %s vs %.3f expected (%.1f%% err, tol %.0f%%)"
        % (got, unit, want, err * 100, tol * 100),
    )


def check_heartbeat(board):
    """Recover the die's real clock from uo[0]. Returns clk_hz or None."""
    f = measure_byte_hz(board, BIT_HEARTBEAT, window_ms=3000)
    want = CLK_HZ / (1 << (BEAT_BIT + 1))
    ok = check_close("heartbeat", f, want, 0.10)
    if not ok or f is None:
        return None
    clk = f * (1 << (BEAT_BIT + 1))
    log("      -> die clock measured %.3f MHz" % (clk / 1e6))
    return clk


def check_frequency_sweep(board, clk_hz, codes=(0, 1, 16, 32, 64, 96, 126, 127)):
    pin = board.uo_pin(BIT_SQUARE)
    if pin is None:
        log("  note: no raw Pin for uo[6]; falling back to byte polling")
    for code in codes:
        board.set_ui(code)
        time.sleep_ms(50)  # let the DDS settle at the new increment
        want = expected_hz(code, clk_hz)
        if pin is not None and want > 20:
            got = measure_pin_hz(pin, timeout_us=int(4e6 / want) + 2000)
        else:
            # ~2 Hz breathe mode: a long polling window beats pulse timing
            got = measure_byte_hz(board, BIT_SQUARE, window_ms=4000)
        check_close("code %-3d square" % code, got, want, 0.08)


def check_level_bar(board, code=64):
    """uo[5:1] must actually move and span most of the offset-binary range."""
    board.set_ui(code)
    time.sleep_ms(50)
    vals = set()
    for b in sample_bytes(board, 4000):
        vals.add((b >> BIT_LEVEL_LSB) & 0x1F)
    span = (max(vals) - min(vals)) if vals else 0
    check(
        "level bar moves",
        len(vals) >= 8 and span >= 20,
        "%d distinct codes, span %d/31" % (len(vals), span),
    )


def check_sigma_delta(board, code=64):
    """Coarse density check on uo[7].

    The RP2040 samples far below the 25 MHz bitstream, so this is aliased and
    only catches a rail-stuck output; a ~50% mean is necessary, not sufficient.
    The authoritative check is an RC filter or the Audio Pmod on a scope.
    """
    board.set_ui(code)
    time.sleep_ms(50)
    samples = sample_bytes(board, 8000)
    ones = sum((b >> BIT_SINE) & 1 for b in samples)
    density = ones / len(samples)
    check(
        "sigma-delta density",
        0.30 < density < 0.70,
        "%.3f (aliased sample, wide tolerance)" % density,
    )


# ---------------------------------------------------------------------- main


def main(clk_hz=CLK_HZ):
    """Full bring-up self-check. Returns True if every check passed."""
    del _results[:]
    log("CORDIC-1 bring-up — %s" % DESIGN)
    board = Board.open()
    board.select()
    board.clock(clk_hz)
    board.reset_pulse()
    log("selected, clock requested %.3f MHz, reset released" % (clk_hz / 1e6))

    log("\n1. proof of life")
    board.set_ui(0)  # wake-up default: untouched pins = concert A
    measured_clk = check_heartbeat(board)
    clk = measured_clk or clk_hz

    log("\n2. DDS frequency sweep (square sync, uo[6])")
    check_frequency_sweep(board, clk)

    log("\n3. engine output")
    check_level_bar(board)
    check_sigma_delta(board)

    failed = [n for n, ok, _ in _results if not ok]
    log("\n%d/%d checks passed" % (len(_results) - len(failed), len(_results)))
    if failed:
        log("FAILED: %s" % ", ".join(failed))
    else:
        log("ALL PASS — put headphones on the Audio Pmod (uo[7]) and listen.")
    board.set_ui(0)
    return not failed


def demo_scale(clk_hz=CLK_HZ, note_ms=400):
    """Play a rising scale on the Audio Pmod — the audible smoke test.

    Codes chosen so the ~68 Hz grid lands near an A-major-ish run; exact
    intonation is not the point, hearing the pitch track the pins is.
    """
    board = Board.open()
    board.select()
    board.clock(clk_hz)
    board.reset_pulse()
    for code in (0, 7, 8, 9, 10, 11, 13, 14, 16, 0):
        board.set_ui(code)
        log("code %3d -> %8.1f Hz" % (code, expected_hz(code, clk_hz)))
        time.sleep_ms(note_ms)
    board.set_ui(127)
    log("code 127 -> breathe mode; watch the LED bar wave")


def sweep_fmax(start_hz=10_000_000, stop_hz=80_000_000, step_hz=5_000_000,
               code=64):
    """Raise the clock until the square sync stops tracking the DDS model.

    Signoff says timing-clean at 50 MHz across corners, nominal Fmax ~115 MHz;
    the RP2040 PWM tops out well below that, so this measures how much of the
    margin the real die actually shows. Prints the last clock that tracked.
    """
    board = Board.open()
    board.select()
    board.reset_pulse()
    pin = board.uo_pin(BIT_SQUARE)
    last_good = None
    hz = start_hz
    while hz <= stop_hz:
        board.clock(hz)
        board.reset_pulse()
        board.set_ui(code)
        time.sleep_ms(50)
        # trust the heartbeat, not the PWM request, for the real clock
        f_beat = measure_byte_hz(board, BIT_HEARTBEAT, window_ms=2000)
        clk = f_beat * (1 << (BEAT_BIT + 1)) if f_beat else hz
        want = expected_hz(code, clk)
        got = (measure_pin_hz(pin, timeout_us=int(4e6 / want) + 2000)
               if pin is not None else
               measure_byte_hz(board, BIT_SQUARE, window_ms=1000))
        ok = got is not None and abs(got - want) / want < 0.08
        log("%6.2f MHz requested / %6.2f MHz measured: square %s"
            % (hz / 1e6, clk / 1e6, "%.1f Hz OK" % got if ok else "BROKEN"))
        if not ok:
            break
        last_good = clk
        hz += step_hz
    board.clock(CLK_HZ)
    board.reset_pulse()
    log("highest tracking clock: %s"
        % ("%.2f MHz" % (last_good / 1e6) if last_good else "none"))
    return last_good


if __name__ == "__main__":
    main()
