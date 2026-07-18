# Exhaustive unit test for the CORDIC engine alone (no SPI, no top):
# every one of the 65536 angles vs Python's math library, plus vector-mode
# atan2/magnitude spot checks.
#   python run_unit.py

import math

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

TOL = 8          # LSB tolerance on sin/cos (Q1.15; truncating shifts)
ATOL = 3         # angle-unit tolerance on atan2 with well-scaled inputs
# atan2 accuracy needs max(|x|,|y|) >= ~8192: below that, x>>i underflows
# before the tail iterations and error grows ~1/|v| (documented; callers
# pre-shift small vectors). Magnitude output valid while hypot*K < 32768.


async def op(dut, mode, zi=0, xi=0, yi=0):
    dut.mode.value = mode
    dut.zi.value = zi & 0xFFFF
    dut.xi.value = xi & 0xFFFF
    dut.yi.value = yi & 0xFFFF
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0
    for _ in range(450):                  # bit-serial: ~340-360 cycles/op
        await RisingEdge(dut.clk)
        if dut.done.value == 1:
            break
    else:
        raise AssertionError("no done pulse")

    def s16(v):
        return v - 0x10000 if v & 0x8000 else v
    return (s16(int(dut.cos_o.value)), s16(int(dut.sin_o.value)),
            s16(int(dut.zo.value)))


@cocotb.test()
async def test_rotate_exhaustive(dut):
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    dut.rst.value = 1
    dut.start.value = 0
    await ClockCycles(dut.clk, 4)
    dut.rst.value = 0

    worst = 0
    for a in range(0, 65536):
        c, s, _ = await op(dut, 0, zi=a)
        rad = a / 65536 * 2 * math.pi
        ec = round(math.cos(rad) * 32766)
        es = round(math.sin(rad) * 32766)
        err = max(abs(c - ec), abs(s - es))
        worst = max(worst, err)
        assert err <= TOL, \
            f"angle {a}: got ({c},{s}) expected ({ec},{es}) err {err}"
    dut._log.info("rotate exhaustive PASS, worst error %d LSB", worst)


@cocotb.test()
async def test_vector_spots(dut):
    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    dut.rst.value = 1
    dut.start.value = 0
    await ClockCycles(dut.clk, 4)
    dut.rst.value = 0

    # bit-serial engine: vector mode covers the RIGHT half-plane (xi >= 0);
    # callers fold the left half in software (negate x,y; add half a turn)
    K = 1.646760258
    pts = [(16000, 0), (0, 16000), (0, -16000),
           (12000, 12000), (9600, -12800), (12000, 5000),
           (18000, 3000), (11000, -11000), (8192, 14000)]
    for xin, yin in pts:
        mag, _, ang = await op(dut, 1, xi=xin, yi=yin)
        ea = round(math.atan2(yin, xin) / (2 * math.pi) * 65536)
        em = round(math.hypot(xin, yin) * K)
        da = min(abs(ang - ea), 65536 - abs(ang - ea))
        assert da <= ATOL, f"atan2({yin},{xin}): got {ang} expected {ea}"
        if em < 32000:      # magnitude saturates near full scale
            assert abs(mag - em) <= 8, \
                f"mag({xin},{yin}): got {mag} expected {em}"

    # a small vector, loose tolerance: documents the 1/|v| behaviour
    _, _, ang = await op(dut, 1, xi=1000, yi=0)
    assert min(abs(ang), 65536 - abs(ang)) <= 16
    dut._log.info("vector spots PASS")
