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

FS = 25e6 / 349          # bit-serial conversion rate at 25 MHz


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
async def test_sigma_delta_density(dut):
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset(dut, code=64)
    await ClockCycles(dut.clk, 4000)

    ones_s = ones_c = 0
    m = 46_000                           # ~8 full periods at code 64
    for _ in range(m):
        await RisingEdge(dut.clk)
        v = int(dut.uo_out.value)
        ones_s += (v >> 7) & 1
        ones_c += (v >> 6) & 1
    assert 0.45 < ones_s / m < 0.55, ones_s / m
    assert 0.45 < ones_c / m < 0.55, ones_c / m
