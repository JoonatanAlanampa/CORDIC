# SPDX-FileCopyrightText: © 2026 Joonatan Alanampa
# SPDX-License-Identifier: Apache-2.0
#
# System-level tests for CORDIC-1: SPI coprocessor ops end to end at the
# pins, and the standalone DDS mode with frequency measurement on the
# sigma-delta output. (The engine itself is exhaustively verified over
# all 65536 angles in unit_cordic.py / run_unit.py.)

import math

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

SCLK = 0
MOSI = 1
CS_N = 2
STANDALONE = 7

HALF = 10  # clk per SPI half-period

REG_CTRL, REG_STATUS = 0x00, 0x01
REG_ANGLE_L, REG_ANGLE_H = 0x02, 0x03
REG_XIN_L, REG_XIN_H, REG_YIN_L, REG_YIN_H = 0x04, 0x05, 0x06, 0x07
REG_COS_L, REG_COS_H, REG_SIN_L, REG_SIN_H = 0x08, 0x09, 0x0A, 0x0B
REG_ZOUT_L, REG_ZOUT_H = 0x0C, 0x0D
REG_ID = 0x7F


def _drive(dut, sclk, mosi, cs_n, hi=0):
    dut.ui_in.value = (sclk << SCLK) | (mosi << MOSI) | (cs_n << CS_N) | hi


async def spi_xfer(dut, rw, addr, data=0):
    word = (rw << 15) | ((addr & 0x7F) << 8) | (data & 0xFF)
    miso_val = 0
    _drive(dut, 0, 0, 0)
    await ClockCycles(dut.clk, HALF)
    for i in range(15, -1, -1):
        bit = (word >> i) & 1
        _drive(dut, 0, bit, 0)
        await ClockCycles(dut.clk, HALF)
        miso_val = (miso_val << 1) | (int(dut.uio_out.value) & 1)
        _drive(dut, 1, bit, 0)
        await ClockCycles(dut.clk, HALF)
    _drive(dut, 0, 0, 1)
    await ClockCycles(dut.clk, HALF)
    return miso_val & 0xFF


async def reg_write(dut, addr, data):
    await spi_xfer(dut, 1, addr, data)


async def reg_read(dut, addr):
    return await spi_xfer(dut, 0, addr)


async def read16(dut, lo_addr):
    lo = await reg_read(dut, lo_addr)
    hi = await reg_read(dut, lo_addr + 1)
    v = (hi << 8) | lo
    return v - 0x10000 if v & 0x8000 else v


async def cordic_op(dut, mode, angle=0, x=0, y=0):
    await reg_write(dut, REG_ANGLE_L, angle & 0xFF)
    await reg_write(dut, REG_ANGLE_H, (angle >> 8) & 0xFF)
    await reg_write(dut, REG_XIN_L, x & 0xFF)
    await reg_write(dut, REG_XIN_H, (x >> 8) & 0xFF)
    await reg_write(dut, REG_YIN_L, y & 0xFF)
    await reg_write(dut, REG_YIN_H, (y >> 8) & 0xFF)
    await reg_write(dut, REG_CTRL, (mode << 1) | 1)
    for _ in range(50):
        if (await reg_read(dut, REG_STATUS)) & 1:
            break
    else:
        raise AssertionError("op never finished")


async def reset(dut):
    dut.ena.value = 1
    _drive(dut, 0, 0, 1)
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)


@cocotb.test()
async def test_id_and_trig(dut):
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset(dut)

    assert await reg_read(dut, REG_ID) == 0xC1

    for angle in (0, 4096, 8192, 16384, 30000, 40000, 54613, 65535):
        await cordic_op(dut, 0, angle=angle)
        c = await read16(dut, REG_COS_L)
        s = await read16(dut, REG_SIN_L)
        rad = angle / 65536 * 2 * math.pi
        assert abs(c - round(math.cos(rad) * 32766)) <= 8, (angle, c)
        assert abs(s - round(math.sin(rad) * 32766)) <= 8, (angle, s)

    # vector: atan2 + magnitude through the pins
    await cordic_op(dut, 1, x=12000, y=5000)
    ang = (await read16(dut, REG_ZOUT_L)) & 0xFFFF
    mag = await read16(dut, REG_COS_L)
    ea = round(math.atan2(5000, 12000) / (2 * math.pi) * 65536)
    assert min(abs(ang - ea), 65536 - abs(ang - ea)) <= 3
    assert abs(mag - round(math.hypot(12000, 5000) * 1.646760258)) <= 8


@cocotb.test()
async def test_standalone_dds(dut):
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    await reset(dut)

    # strap standalone, freq code 64 -> f = 64*1024/2^24 * (25e6/18) ~ 5.43 kHz
    code = 64
    dut.ui_in.value = (1 << STANDALONE) | code
    await ClockCycles(dut.clk, 2000)      # let the DDS spin up

    # measure via sign flips of the LED bar MSB (uo[5] = sign of sine)
    flips = 0
    prev = (int(dut.uo_out.value) >> 5) & 1
    n = 60000
    for _ in range(n):
        await RisingEdge(dut.clk)
        cur = (int(dut.uo_out.value) >> 5) & 1
        if cur != prev:
            flips += 1
        prev = cur

    t = n * 40e-9
    f_meas = flips / 2 / t
    f_exp = code * 1024 / 2**24 * (25e6 / 18)
    assert abs(f_meas - f_exp) / f_exp < 0.1, (f_meas, f_exp)
    dut._log.info("standalone DDS: measured %.1f Hz, expected %.1f Hz",
                  f_meas, f_exp)

    # sigma-delta density sanity: over full periods, sine averages to ~50%
    # (uo[7]: the TT Audio Pmod listens there)
    ones = 0
    m = 46000                             # ~10 periods
    for _ in range(m):
        await RisingEdge(dut.clk)
        ones += (int(dut.uo_out.value) >> 7) & 1
    duty = ones / m
    assert 0.45 < duty < 0.55, duty
