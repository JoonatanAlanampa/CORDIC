# SPDX-FileCopyrightText: © 2026 Joonatan Alanampa
# SPDX-License-Identifier: Apache-2.0
#
# System tests for CORDIC-1 (1x1 instrument-only): frequency measurement
# on the pins for the 440 Hz wake-up default and a mid-range code, plus
# sigma-delta density sanity. (The engine is exhaustively verified over
# all 65536 angles in unit_cordic.py / run_unit.py.)

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

FS = 25e6 / 359          # constant-time bit-serial conversion rate at 25 MHz


async def reset(dut, code):
    dut.ena.value = 1
    dut.ui_in.value = code
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1


async def measure_hz(dut, cycles):
    """Frequency via sign flips of the LED bar MSB (uo[5])."""
    flips = 0
    prev = (int(dut.uo_out.value) >> 5) & 1
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        cur = (int(dut.uo_out.value) >> 5) & 1
        if cur != prev:
            flips += 1
        prev = cur
    return flips / 2 / (cycles * 40e-9)


@cocotb.test()
async def test_wakeup_440(dut):
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset(dut, code=0)             # untouched pins = the default tone
    await ClockCycles(dut.clk, 4000)

    f = await measure_hz(dut, 300_000)   # ~5 periods of 440 Hz
    assert abs(f - 440) / 440 < 0.12, f
    dut._log.info("wake-up tone: measured %.1f Hz (target 440)", f)


@cocotb.test()
async def test_code64(dut):
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset(dut, code=64)
    await ClockCycles(dut.clk, 4000)

    f = await measure_hz(dut, 60_000)
    f_exp = 64 * 1024 / 2**20 * FS       # ~4.48 kHz
    assert abs(f - f_exp) / f_exp < 0.1, (f, f_exp)
    dut._log.info("code 64: measured %.1f Hz, expected %.1f Hz", f, f_exp)


@cocotb.test()
async def test_sigma_delta_and_sync(dut):
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset(dut, code=64)
    await ClockCycles(dut.clk, 4000)

    # sine sigma-delta density ~50% over full periods; square sync on
    # uo[6] flips twice per period, phase-locked to the DDS
    ones_s = flips = 0
    prev = (int(dut.uo_out.value) >> 6) & 1
    m = 46_000                           # ~8 full periods at code 64
    for _ in range(m):
        await RisingEdge(dut.clk)
        v = int(dut.uo_out.value)
        ones_s += (v >> 7) & 1
        cur = (v >> 6) & 1
        if cur != prev:
            flips += 1
        prev = cur
    assert 0.45 < ones_s / m < 0.55, ones_s / m
    f_sync = flips / 2 / (m * 40e-9)
    f_exp = 64 * 1024 / 2**20 * FS
    assert abs(f_sync - f_exp) / f_exp < 0.1, (f_sync, f_exp)


@cocotb.test()
async def test_spectrum(dut):
    """FFT the sigma-delta bitstream: fundamental on target, harmonics
    low. Guards the constant-time schedule — data-dependent op timing
    would phase-modulate the sample rate and grow fold-correlated
    harmonics (the flaw this test was written to catch)."""
    import numpy as np

    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset(dut, code=64)              # ~4352 Hz
    await ClockCycles(dut.clk, 4000)

    n = 1 << 17                            # 131072 samples = ~5.2 ms, ~23 periods
    bits = np.empty(n, dtype=np.float64)
    for j in range(n):
        await RisingEdge(dut.clk)
        bits[j] = (int(dut.uo_out.value) >> 7) & 1

    x = bits - bits.mean()
    spec = np.abs(np.fft.rfft(x * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, d=40e-9)

    f0 = 64 * 1024 / 2**20 * FS
    def peak_near(f, width=6):
        i = int(round(f / freqs[1]))
        lo, hi = max(i - width, 1), i + width
        return spec[lo:hi].max()

    fund = peak_near(f0)
    i_meas = np.argmax(spec[1:len(spec) // 4]) + 1
    assert abs(freqs[i_meas] - f0) / f0 < 0.02, (freqs[i_meas], f0)

    worst_dbc = -100.0
    for h in range(2, 6):
        dbc = 20 * np.log10(peak_near(h * f0) / fund)
        worst_dbc = max(worst_dbc, dbc)
    dut._log.info("spectrum: fundamental %.1f Hz, worst harmonic %.1f dBc",
                  freqs[i_meas], worst_dbc)
    assert worst_dbc < -40, f"harmonic at {worst_dbc:.1f} dBc"
