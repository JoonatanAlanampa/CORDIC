# CORDIC-1 test suite

Three layers, all runnable on Windows without `make`:

```
python run_unit.py   # EXHAUSTIVE engine test: all 65,536 angles vs Python's
                     # math library (worst error 5 LSB), plus vector-mode
                     # spot checks. ~15 minutes.

python run.py        # System tests at the chip pins:
                     #   - 440 Hz wake-up tone measured (code 0)
                     #   - code-64 frequency vs the DDS formula
                     #   - sigma-delta density + square-sync frequency lock
                     #   - FFT spectral test: worst harmonic < -40 dBc
                     #     (measures -65 dBc; guards the constant-time
                     #     schedule against sample-jitter regressions)
```

Formal verification (control-path k-induction proof + deep BMC witnesses)
lives in [`../formal/`](../formal/) — see `cordic.sby`.

CI runs the system tests on every push (`test` workflow) and re-runs them
against the post-layout gate-level netlist (`gl_test` job of the `gds`
workflow). `requirements.txt` pins the Python deps, including numpy for
the FFT test.

The classic cocotb + Makefile flow also works (`make -B`, Unix
environments); waveforms land in `tb.fst` for GTKWave/Surfer. See the
[TinyTapeout testing guide](https://tinytapeout.com/hdl/testing/).
