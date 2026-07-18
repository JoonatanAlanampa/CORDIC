// ulx3s_top.sv — ULX3S 85F verification harness for CORDIC-1.
//
// The ASIC module tt_um_joonatanalanampa_cordic is instantiated UNCHANGED:
// what runs on the FPGA is bit-for-bit the RTL that gets hardened. This
// wrapper only adapts the board:
//
//   clk_25mhz  -> clk (the ASIC's assumed frequency, exactly)
//   btn[0]     -> reset (press = reset; it is the pulled-up PWR button)
//   sw[0]      -> STANDALONE strap (on = DDS mode, off = SPI coprocessor)
//   btn[3]/[4] -> frequency code up/down (wrapper-side register, ~8 steps/s)
//   led[7:0]   -> uo (sine level bar on led[5:1], done on led[0];
//                 led[7]/led[6] glow ~half bright with the sigma-deltas)
//   audio jack -> left = sine, right = cosine (board's 4-bit DAC, driven
//                 by the 1-bit sigma-delta streams: headphones welcome)
//   gp[0..2]   -> SPI SCLK / MOSI / CS_n in from an external master
//   gn[0]      -> SPI MISO out
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
    input  wire [2:0] gp,        // SPI: SCLK, MOSI, CS_n
    output wire       gn0,       // SPI: MISO
    output wire       wifi_gpio0
);

  assign wifi_gpio0 = 1'b1;      // keep the board powered on

  wire clk   = clk_25mhz;
  wire rst_n = btn[0];           // pulled up; pressing pulls low = reset

  // wrapper-side frequency code, stepped by the up/down buttons
  logic [6:0]  freq_code = 7'd32;
  logic [21:0] tick;             // ~6 Hz repeat at 25 MHz
  always_ff @(posedge clk) begin
    tick <= tick + 22'd1;
    if (tick == 22'd0) begin
      if (btn[3] && freq_code != 7'd127) freq_code <= freq_code + 7'd1;
      if (btn[4] && freq_code != 7'd1)   freq_code <= freq_code - 7'd1;
    end
  end

  wire [7:0] ui_in = sw[0] ? {1'b1, freq_code}
                           : {5'b00000, gp[2], gp[1], gp[0]};

  wire [7:0] uo_out, uio_out, uio_oe, uio_in;
  assign uio_in = 8'h00;

  tt_um_joonatanalanampa_cordic dut (
      .ui_in  (ui_in),
      .uo_out (uo_out),
      .uio_in (uio_in),
      .uio_out(uio_out),
      .uio_oe (uio_oe),
      .ena    (1'b1),
      .clk    (clk),
      .rst_n  (rst_n)
  );

  assign led = uo_out;
  assign gn0 = uio_out[0];       // MISO

  // 1-bit sigma-delta streams into the board's 4-bit resistor DAC
  assign audio_l = {4{uo_out[7]}};   // sine
  assign audio_r = {4{uo_out[6]}};   // cosine

endmodule
