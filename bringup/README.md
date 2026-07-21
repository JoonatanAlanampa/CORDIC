# Silicon bring-up — CORDIC-1 on the TinyTapeout demo board

MicroPython that runs on the demo board's RP2040 and self-checks the die on
the pins. It is the fifth verification layer: simulation, formal, spectral and
gate-level all ran before tapeout — this one runs *after*, on the chip that
came back from the fab.

| file | what it is |
|---|---|
| `cordic1_bringup.py` | the script you copy to the demo board |
| `test_bringup_host.py` | CPython test: runs the script against a virtual die, plus three broken dice it must reject |

## Running it on hardware

Copy `cordic1_bringup.py` to the board's filesystem (Thonny, `mpremote cp`,
or the board's web REPL), then at the REPL:

```python
>>> import cordic1_bringup as bu
>>> bu.main()          # full self-check, PASS/FAIL table, returns True/False
>>> bu.demo_scale()    # audible smoke test: plays a rising scale
>>> bu.sweep_fmax()    # raise the clock until the DDS stops tracking
```

`main()` selects the design, sets the 25 MHz ship clock, pulses reset, and
then only ever touches `ui_in` and reads `uo_out` — CORDIC-1 has no bus, so
the pins are the whole interface.

Nothing needs to be plugged in for `main()` to pass. For the parts a human
has to judge, add the **Audio Pmod** (it listens on `uo[7]`, exactly where the
sine is) or an RC low-pass (1 kΩ + 100 nF) into a scope.

## What each check proves

0. **ui_in drive** — walks a one across the seven frequency pins and reads
   them back. The firmware will not take over a `ui_in` pin that is already
   reading HIGH (contention protection): it logs an error and leaves the pin
   an input, so a DIP switch left on silently vetoes that bit and every
   frequency below it comes out wrong for a reason that has nothing to do
   with the die. This check names the offending pin instead.
1. **heartbeat** — `uo[0]` is bit 23 of a free-running counter, so its
   frequency is `clk / 2**24`. Measuring it recovers the clock the die
   *really* sees; every later expectation is computed from that measured
   clock, not from the frequency the RP2040 PWM was asked for. If this fails,
   the design is not selected, not clocked, or still in reset.
2. **DDS frequency sweep** — `uo[6]` is `phase[19]`, a square at the output
   frequency. Eight codes (0, 1, 16, 32, 64, 96, 126, 127) are checked
   against `inc(code)/2**20 * clk/359` from `src/project.sv`. This exercises
   the input pins, the DDS accumulator and the constant-time CORDIC schedule
   in one measurement — the 359-cycle period is what makes the arithmetic
   exact, so a wrong frequency here means the engine, not just the counter.
   Codes 0 and 127 are the special cases (440 Hz wake-up tone, ~2 Hz breathe).
3. **level bar** — `uo[5:1]`, the live sine sample in offset binary. Must
   move and span most of its range; a die whose DDS ticks but whose engine is
   dead shows a stuck or rail-parked bar.
4. **sigma-delta density** — `uo[7]` should average ~50% over whole periods.
   The RP2040 samples far below the 25 MHz bitstream, so this reading is
   aliased and the tolerance is deliberately wide: it catches a rail-stuck
   output and nothing finer. The real verdict is the scope or your ears.

`sweep_fmax()` is the one number simulation cannot give: signoff says
timing-clean at 50 MHz across all corners with a nominal Fmax of ~115 MHz, and
this measures how much of that margin the actual silicon shows. It trusts the
heartbeat for the true clock at each step, since the RP2040's PWM cannot hit
arbitrary frequencies exactly.

## Testing it without a chip

The chips arrive ~mid-2027. Until then:

```
python bringup/test_bringup_host.py
```

This stubs `machine`, `time` and `ttboard.demoboard` with a virtual demo board
whose pins follow the model in `src/project.sv` (including 1 µs pulse-timer
quantisation and a finite polling rate), then runs the *unmodified* script
against it. A good die must pass all 12 checks; a dead DDS, a stuck level bar,
a rail-parked sigma-delta and a DIP switch vetoing an input pin must each be
caught — a bring-up script that cannot fail proves nothing.

Point `TT_FIRMWARE_SRC` at a `tt-micropython-firmware` checkout's
`microcotb/src` and the virtual board wires up the **real** microcotb `IO`
port class instead of a stand-in, so the script's read/write idioms run
against shipping firmware code. CI does this at a pinned commit
(`f34d9f0`); bump that ref deliberately, since a diff there is exactly the
API drift worth seeing. If the variable is set but the import fails the test
dies rather than falling back — the first version of this swallowed that
error and reported a green run that had quietly used the stand-in, which is
worse than no check at all. The `ports:` line at the top of the output says
which class actually ran.

## Firmware compatibility

Written against **tt-micropython-firmware v2.0.0** (`f34d9f0`, microcotb
`81f2498`), with the API read rather than assumed. What that reading changed:

- `tt.ui_in` / `tt.uo_out` are microcotb `IO` ports, not ints — read with
  `int(port)`, write with `port.value = x`. `tt.ui_in = x` also works, because
  `DemoBoard.__setattr__` forwards it to the port.
- `port[i]` returns a sampled **Logic bit** (LSB-indexed), *not* a pin. An
  earlier draft of this script used `tt.uo_out[6]` as a `machine.Pin` for
  `time_pulse_us` — it would have failed on the bench. Raw pins live at
  `tt.pins.uo_out<N>.raw_pin`.
- `clock_project_PWM()` retunes the RP2040 **system clock** to reach the
  requested frequency and settles for a nearby one if it cannot — vindicating
  the decision to derive everything from the measured heartbeat. (The RP2040's
  microsecond timer runs off the reference clock, not the system clock, so
  `time.ticks_us` stays honest across that retune.)
- Design lookup goes `shuttle.has()` / `shuttle.get()` first, then attribute
  access, then `find()`.

The API has still drifted between releases and the chips land ~mid-2027, so
every board call goes through the `Board` shim and falls back. **If a future
firmware breaks this, `Board` is the only part that needs editing.** Two
fallbacks worth knowing:

- If the board cannot be put into `ASIC_RP_CONTROL` the script says so and
  keeps going — set the input DIP switches by hand and the frequency sweep
  still reads out, it just cannot change codes itself.
- If no raw `machine.Pin` can be resolved for `uo[6]`, measurement falls back
  to polling the output byte. That is accurate for the heartbeat and the low
  codes; expect the top codes (~8.6 kHz) to be under-sampled.
