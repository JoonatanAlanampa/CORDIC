# Unit-level runner: the cordic engine as the simulation toplevel.
#   python run_unit.py

from pathlib import Path

from cocotb_tools.runner import get_runner

TEST_DIR = Path(__file__).parent
SRC_DIR = TEST_DIR.parent / "src"


def main():
    runner = get_runner("icarus")
    runner.build(
        sources=[SRC_DIR / "cordic.sv"],
        hdl_toplevel="cordic",
        build_dir=TEST_DIR / "sim_build" / "unit",
        build_args=["-g2012"],
        timescale=("1ns", "1ps"),
    )
    runner.test(
        hdl_toplevel="cordic",
        test_module="unit_cordic",
        test_dir=TEST_DIR,
    )


if __name__ == "__main__":
    main()
