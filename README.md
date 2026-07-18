![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/fpga/badge.svg)

# CORDIC-1 — a one-tile sine generator that wakes up singing

Standalone sine-generator instrument chip for TinyTapeout Sky130: a
bit-serial CORDIC engine (verified exhaustively — all 65,536 angles, worst
error 5 LSB) swept by a DDS, streaming sigma-delta sine on the Audio Pmod
pin. Powers up playing 440 Hz concert A; 127 switch-selectable frequencies
(~70 Hz–8.8 kHz), a ~2 Hz LED breathe mode, a phase-locked square sync,
and a heartbeat pilot light. 921 cells, one tile, no bus, no host, no
software.

- **[Interactive die viewer (2D/3D)](https://joonatanalanampa.github.io/CORDIC/)** — pan around the actual GDS layout
- [Datasheet](docs/info.md) — pinout, frequency table, bring-up
- [Formal proof](formal/) — SymbiYosys k-induction over the engine's
  control path (never hangs, exact schedule, single done per op), on top
  of the exhaustive 65,536-angle simulation
- **Prebuilt ULX3S bitstream**: [`fpga/build/cordic_ulx3s.bit`](fpga/build/cordic_ulx3s.bit) — flash and listen, no toolchain needed

## PPA (from signoff, SkyWater 130 nm, nominal tt/25C/1.80V)

| | |
|---|---|
| **Power** | ~0.56 mW at the 25 MHz ship clock (OpenSTA estimate at 50 MHz: 1.12 mW, 47% clock tree; leakage 7.8 nW — 0.0007%). A coin cell could hum concert A for ~50 days. |
| **Performance** | Ships at 25 MHz; signoff-clean at 50 MHz across all corners (incl. ss/100C/1.60V); nominal Fmax ~115 MHz. ~72k sine conversions/s, latency 338–359 cycles (formally proven <= 358). |
| **Area** | 1 tile = 167x108 um ~ 0.018 mm^2; 921 standard cells (~240 flops), 74.0% utilization. |

The bit-serial trade in one line: ~20x less throughput than the parallel
engine (irrelevant — the 72 kHz DDS is fully fed) for 2.6x less area
(194% -> 74% of a tile) and 4.6x clock margin from 1-bit-adder paths.
- [FPGA harness](fpga/) — verify the exact ASIC RTL on a ULX3S 85F
  (`powershell -File fpga\synth.ps1`, then `openFPGALoader -b ulx3s fpga\build\cordic_ulx3s.bit`)

## What is Tiny Tapeout?

Tiny Tapeout is an educational project that aims to make it easier and cheaper than ever to get your digital and analog designs manufactured on a real chip.

To learn more and get started, visit https://tinytapeout.com.

## Set up your Verilog project

1. Add your Verilog files to the `src` folder.
2. Edit the [info.yaml](info.yaml) and update information about your project, paying special attention to the `source_files` and `top_module` properties. If you are upgrading an existing Tiny Tapeout project, check out our [online info.yaml migration tool](https://tinytapeout.github.io/tt-yaml-upgrade-tool/).
3. Edit [docs/info.md](docs/info.md) and add a description of your project.
4. Adapt the testbench to your design. See [test/README.md](test/README.md) for more information.

The GitHub action will automatically build the ASIC files using [LibreLane](https://www.zerotoasiccourse.com/terminology/librelane/).

## Enable GitHub actions to build the results page

- [Enabling GitHub Pages](https://tinytapeout.com/faq/#my-github-action-is-failing-on-the-pages-part)

## Resources

- [FAQ](https://tinytapeout.com/faq/)
- [Digital design lessons](https://tinytapeout.com/digital_design/)
- [Learn how semiconductors work](https://tinytapeout.com/siliwiz/)
- [Join the community](https://tinytapeout.com/discord)
- [Build your design locally](https://www.tinytapeout.com/guides/local-hardening/)

## What next?

- [Submit your design to the next shuttle](https://app.tinytapeout.com/).
- Edit [this README](README.md) and explain your design, how it works, and how to test it.
- Share your project on your social network of choice:
  - LinkedIn [#tinytapeout](https://www.linkedin.com/search/results/content/?keywords=%23tinytapeout) [@TinyTapeout](https://www.linkedin.com/company/100708654/)
  - Mastodon [#tinytapeout](https://chaos.social/tags/tinytapeout) [@matthewvenn](https://chaos.social/@matthewvenn)
  - X (formerly Twitter) [#tinytapeout](https://twitter.com/hashtag/tinytapeout) [@tinytapeout](https://twitter.com/tinytapeout)
  - Bluesky [@tinytapeout.com](https://bsky.app/profile/tinytapeout.com)
