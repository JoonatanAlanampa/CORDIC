## How it works

CORDIC-1 is a **trigonometry coprocessor and standalone sine generator**
built around a 16-iteration serial CORDIC engine — sin, cos, atan2 and
vector magnitude from nothing but shifts and adds (no multipliers). The
engine carries 2 guard bits on all three accumulators and is verified
**exhaustively**: all 65,536 input angles against reference math, worst
error 4 LSB of Q1.15.

**Coprocessor mode** (SPI mode 0, 16-bit transactions: command byte
`{rw, addr}` + data byte): write a 16-bit angle (65536 = full turn) into
ANGLE, set CTRL.start, and 18 clocks later read sin/cos from the result
registers. Vector mode (CTRL.mode=1) takes a point (XIN, YIN) and returns
atan2 in ZOUT and K*magnitude (K=1.6468) in COS. For full atan2 accuracy
present inputs scaled so max(|x|,|y|) >= 8192. ID register 0x7F reads
0xC1.

**Standalone mode** (strap ui[7] high — no host of any kind): a 24-bit
DDS phase accumulator sweeps the engine continuously (~1.4 M
conversions/s) and first-order sigma-delta modulators stream the sine on
uo[7] (exactly where the TT Audio Pmod listens) and quadrature cosine on
uo[6]. An external RC low-pass (1k +
100 nF works) turns each into a clean analog sine wave. ui[6:0] set the
frequency, ~85 Hz per step (measured 5.21 kHz at code 64, 25 MHz clock)
— flip DIP switches, get a precision function generator. The same DDS is
software-controllable over SPI (DDS_INC, ~21 Hz/LSB; DDS_CTRL.0 enable).

uo[5:1] show the live sine level as an offset-binary bar — at low
frequencies the LEDs visibly breathe.

## How to test

Read register 0x7F over SPI — it must return 0xC1. Write ANGLE=0x2000
(45 deg), CTRL=0x01, then read SIN/COS: both ~23170 (0.707). Or skip SPI
entirely: tie ui[7] high with a frequency code on ui[6:0], put an RC
filter on uo[7], and watch a sine on a scope (or listen to it — audio
range). The uo[5:1] level bar breathes at the output frequency.

## External hardware

None required (LED bar works bare). For analog output: an RC low-pass on
uo[7]/uo[6] — or the Tiny Tapeout audio Pmod. Any SPI master (demo board
RP2040, Arduino) for coprocessor mode.
