# SPDX-FileCopyrightText: © 2026 Joonatan Alanampa
# SPDX-License-Identifier: Apache-2.0
"""
Host-side test for cordic1_bringup.py — run on CPython, no hardware.

The chips land ~mid-2027, so the bring-up script would otherwise sit untested
for a year. This stubs `machine`, `time` and `ttboard.demoboard` with a virtual
demo board whose pins follow the CORDIC-1 pin model from src/project.sv, then
runs the real script against it:

  * a GOOD die must pass every check;
  * three broken dice (dead DDS, stuck level bar, rail-parked sigma-delta)
    must each be caught — a bring-up script that cannot fail is worthless.

    python bringup/test_bringup_host.py
"""

import math
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CLK_HZ = 25_000_000
OPS_DIV = 359
POLL_US = 40.0  # cost of one output-byte read, i.e. the polling sample rate


# ------------------------------------------------------------ virtual clock
class VClock:
    def __init__(self):
        self.us = 0.0

    def advance(self, us):
        self.us += us


CLOCK = VClock()


def _dds_inc(code):
    if code == 0:
        return 6625
    if code == 127:
        return 30
    return code << 10


# ------------------------------------------------------------- die behaviour
class Die:
    """Pin-level model of tt_um_joonatanalanampa_cordic."""

    def __init__(self, fault=None):
        self.clk = CLK_HZ
        self.code = 0
        self.t_reset = 0.0
        self.fault = fault
        self._lcg = 12345

    # --- derived frequencies ------------------------------------------
    @property
    def f_beat(self):
        return self.clk / (1 << 24)

    @property
    def f_out(self):
        if self.fault == "dead_dds":
            return 1.0  # DDS stuck near DC whatever the code says
        return _dds_inc(self.code) / (1 << 20) * (self.clk / OPS_DIV)

    # --- pin values at the current virtual time -------------------------
    def _t(self):
        return (CLOCK.us - self.t_reset) / 1e6

    def square(self, f, t=None):
        t = self._t() if t is None else t
        return 1 if (f * t) % 1.0 < 0.5 else 0

    def sine(self):
        return math.sin(2 * math.pi * self.f_out * self._t())

    def byte(self):
        s = self.sine()
        if self.fault == "stuck_bar":
            level = 0
        else:
            level = int((s + 1.0) / 2.0 * 31.0) & 0x1F
        if self.fault == "stuck_sd":
            sd = 1
        else:
            self._lcg = (self._lcg * 1103515245 + 12345) & 0x7FFFFFFF
            sd = 1 if (self._lcg / 0x7FFFFFFF) < (s + 1.0) / 2.0 else 0
        return (
            (sd << 7)
            | (self.square(self.f_out) << 6)
            | (level << 1)
            | self.square(self.f_beat)
        )

    def bit_freq(self, bit):
        """Frequency of a bit that is a clean square (used by time_pulse_us)."""
        if bit == 0:
            return self.f_beat
        if bit == 6:
            return self.f_out
        raise AssertionError("time_pulse_us used on a non-square bit %d" % bit)


DIE = Die()


# ------------------------------------------------------------- fake `machine`
class FakePin:
    def __init__(self, bit):
        self.bit = bit

    def value(self):
        CLOCK.advance(POLL_US)
        return (DIE.byte() >> self.bit) & 1


def fake_time_pulse_us(pin, level, timeout_us=1_000_000):
    """Analytic pulse timer: advance virtual time to the next `level` pulse."""
    f = DIE.bit_freq(pin.bit)
    half_us = 1e6 / (2.0 * f)
    if 2 * half_us > timeout_us:
        CLOCK.advance(timeout_us)
        return -2  # MicroPython's timeout return
    t = (CLOCK.us - DIE.t_reset) / 1e6
    frac = (f * t) % 1.0
    # time until the start of the next pulse at the requested level
    target = 0.0 if level else 0.5
    delta = (target - frac) % 1.0
    CLOCK.advance(delta / f * 1e6)  # skip to the pulse start
    CLOCK.advance(half_us)  # ... and through the pulse
    return int(round(half_us))  # 1 us quantisation, as on real hardware


machine = types.ModuleType("machine")
machine.Pin = FakePin
machine.time_pulse_us = fake_time_pulse_us
sys.modules["machine"] = machine


# ---------------------------------------------------------------- fake `time`
faketime = types.ModuleType("time")
faketime.sleep_ms = lambda ms: CLOCK.advance(ms * 1000.0)
faketime.ticks_us = lambda: int(CLOCK.us)
faketime.ticks_diff = lambda a, b: a - b
sys.modules["time"] = faketime


# ------------------------------------------------------- fake ttboard package
class FakeByteReg:
    def __init__(self, setter=None, getter=None):
        self._set, self._get = setter, getter

    @property
    def value(self):
        return self._get()

    @value.setter
    def value(self, v):
        self._set(v)

    def __getitem__(self, i):
        return FakePin(i)


class FakeProject:
    def __init__(self, name):
        self.name = name
        self.enabled = False

    def enable(self):
        self.enabled = True


class FakeShuttle:
    def __init__(self):
        setattr(self, "tt_um_joonatanalanampa_cordic",
                FakeProject("tt_um_joonatanalanampa_cordic"))


class FakeDemoBoard:
    def __init__(self):
        self.shuttle = FakeShuttle()
        self.mode = None
        self.ui_in = FakeByteReg(setter=self._set_ui, getter=lambda: DIE.code)
        self.uo_out = FakeByteReg(getter=self._get_uo)

    def _set_ui(self, v):
        DIE.code = v & 0x7F

    def _get_uo(self):
        CLOCK.advance(POLL_US)
        return DIE.byte()

    def clock_project_PWM(self, hz):
        DIE.clk = hz

    def clock_project_stop(self):
        pass

    def reset_project(self, asserted):
        if not asserted:
            DIE.t_reset = CLOCK.us

    @classmethod
    def get(cls):
        return cls()


ttboard = types.ModuleType("ttboard")
demoboard = types.ModuleType("ttboard.demoboard")
demoboard.DemoBoard = FakeDemoBoard
mode_mod = types.ModuleType("ttboard.mode")


class RPMode:
    ASIC_RP_CONTROL = "ASIC_RP_CONTROL"


mode_mod.RPMode = RPMode
ttboard.demoboard = demoboard
ttboard.mode = mode_mod
sys.modules["ttboard"] = ttboard
sys.modules["ttboard.demoboard"] = demoboard
sys.modules["ttboard.mode"] = mode_mod


# --------------------------------------------------------------------- tests
import cordic1_bringup as bu  # noqa: E402  (must follow the stubs)


def run(fault=None):
    global DIE
    DIE = Die(fault)
    CLOCK.us = 0.0
    ok = bu.main()
    failed = [n for n, passed, _ in bu._results if not passed]
    return ok, failed


def main():
    print("=" * 70)
    print("GOOD DIE")
    print("=" * 70)
    ok, failed = run()
    assert ok, "good die must pass every check, but these failed: %s" % failed

    for fault, must_catch in (
        ("dead_dds", "code"),
        ("stuck_bar", "level bar moves"),
        ("stuck_sd", "sigma-delta density"),
    ):
        print("\n" + "=" * 70)
        print("FAULT INJECTED: %s" % fault)
        print("=" * 70)
        ok, failed = run(fault)
        assert not ok, "%s die was reported healthy" % fault
        assert any(must_catch in f for f in failed), (
            "%s die failed the wrong checks: %s" % (fault, failed))
        print("-> correctly caught by: %s" % ", ".join(failed))

    print("\nALL HOST TESTS PASSED")


if __name__ == "__main__":
    main()
