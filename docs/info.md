## How it works

CORDIC-1 is a **standalone sine and cosine generator** in one TinyTapeout
tile — a self-playing instrument with no bus, no host, and no software.
Select it, release reset, and it plays.

Inside: a **bit-serial CORDIC engine** (x, y, z as 20-bit shift registers
circulating LSB-first through three 1-bit full adders — sin and cos from
nothing but shifts and adds, ~350 clocks per conversion, ~72k
conversions/s at 25 MHz). The engine is verified **exhaustively**: all
65,536 input angles against reference math, worst error 5 LSB of Q1.15.
A 20-bit DDS phase accumulator sweeps it continuously, and two
first-order sigma-delta modulators stream the results: **sine on uo[7]**
(exactly where the TT Audio Pmod listens) and **quadrature cosine on
uo[6]**. An RC low-pass (1 kOhm + 100 nF) per pin — or the Audio Pmod —
turns each into a clean analog wave.

Frequency is set live by ui[6:0]:

| code | output |
|---|---|
| 0 (power-on default) | **440 Hz — concert A wake-up tone** |
| 1..126 | code x ~70 Hz (~70 Hz .. ~8.8 kHz) |
| 127 | ~2 Hz breathe mode: the LED bar visibly waves |

uo[5:1] show the live sine level as an offset-binary LED bar, and uo[0]
blinks a ~1.5 Hz **heartbeat** — proof of life visible with nothing
attached at all.

## How to test

Power on, select the design, release reset: the heartbeat LED blinks and
the level bar shimmers immediately — with headphones on the Audio Pmod
you hear concert A. Scope the RC-filtered uo[7]: a 440 Hz sine. Change
ui[6:0]: the pitch follows, ~70 Hz per step. Set all ones (127): the LED
bar breathes a slow visible wave. Scope uo[7] vs uo[6] in XY mode: a
circle — sin^2 + cos^2 = 1, drawn by the silicon.

## External hardware

None required (heartbeat + LED bar work bare). For analog output: an RC
low-pass on uo[7]/uo[6], or the Tiny Tapeout Audio Pmod (it listens on
uo[7]). DIP switches or the demo board's inputs for ui[6:0].
