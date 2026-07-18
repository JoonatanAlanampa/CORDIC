// ulx3s_top.sv — ULX3S 85F verification harness for CORDIC-1 (1x1
// instrument-only version).
//
// The ASIC module tt_um_joonatanalanampa_cordic is instantiated UNCHANGED:
// what runs on the FPGA is bit-for-bit the RTL that gets hardened.
//
//   clk_25mhz  -> clk (the ASIC's assumed frequency, exactly)
//   btn[0]     -> reset (press = reset; it is the pulled-up PWR button)
//   btn[3]/[4] -> frequency code up/down (~6 steps/s while held);
//                 power-on code 0 = the 440 Hz wake-up tone,
//                 code 127 (hold up) = ~2 Hz LED breathe mode
//   led[7:0]   -> uo: sine level bar on led[5:1], heartbeat on led[0],
//                 led[7]/led[6] carry the sigma-deltas (~half bright)
//   audio jack -> left = sine, right = cosine (board 4-bit DAC)
//
// Copyright (c) 2026 Joonatan Alanampa
// SPDX-License-Identifier: Apache-2.0

`default_nettype none

module ulx3s_top (
    input  wire       clk_25mhz,
    input  wire [6:0] btn,
    input  wire [3:0] sw,
    output wire [7:0] led,
    output wire [3:0] audio_l,
    output wire [3:0] audio_r,
    output wire       wifi_gpio0
);

  assign wifi_gpio0 = 1'b1;      // keep the board powered on

  wire clk   = clk_25mhz;
  wire rst_n = btn[0];           // pulled up; pressing pulls low = reset

  // wrapper-side frequency code, stepped by the up/down buttons
  logic [6:0]  freq_code = 7'd0; // power-on: the 440 Hz wake-up default
  logic [21:0] tick;             // ~6 Hz repeat at 25 MHz
  always_ff @(posedge clk) begin
    tick <= tick + 22'd1;
    if (tick == 22'd0) begin
      if (btn[3] && freq_code != 7'd127) freq_code <= freq_code + 7'd1;
      if (btn[4] && freq_code != 7'd0)   freq_code <= freq_code - 7'd1;
    end
  end

  wire [7:0] uo_out, uio_out, uio_oe;

  tt_um_joonatanalanampa_cordic dut (
      .ui_in  ({1'b0, freq_code}),
      .uo_out (uo_out),
      .uio_in (8'h00),
      .uio_out(uio_out),
      .uio_oe (uio_oe),
      .ena    (1'b1),
      .clk    (clk),
      .rst_n  (rst_n)
  );

  assign led = uo_out;

  // 1-bit sigma-delta streams into the board's 4-bit resistor DAC
  assign audio_l = {4{uo_out[7]}};   // sine
  assign audio_r = {4{uo_out[6]}};   // square sync: timbre A/B vs the sine

  wire _unused = &{sw, uio_out, uio_oe, 1'b0};

endmodule
