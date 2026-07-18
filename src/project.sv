/*
 * CORDIC-1: trig coprocessor + standalone DDS sine generator, one tile.
 *
 * Two personalities:
 *  - Coprocessor (SPI mode 0, same interface family as ServoCtl-8):
 *    write an angle, read sin/cos 18 cycles later; or write a point,
 *    read atan2 + magnitude. 16-bit fixed point, +/-4 LSB (exhaustively
 *    verified).
 *  - Standalone (strap ui[7] high): a DDS sweeps phase at a rate set by
 *    ui[6:0] (~85 Hz .. ~10.8 kHz at 25 MHz), the engine computes sine
 *    continuously, and 1-bit sigma-delta streams on uo[0] (sin) and
 *    uo[1] (cos, quadrature) become clean analog through an RC filter.
 *    No host needed: flip switches, get a precision sine wave.
 *    SPI can also drive the DDS (DDS_INC, ~21.2 Hz/LSB) when strapped low.
 *
 * Pinout:
 *   ui[0] SPI SCLK   ui[7]   STANDALONE strap
 *   ui[1] SPI MOSI   ui[6:0] standalone frequency (when strapped)
 *   ui[2] SPI CS_n   uio[0]  SPI MISO
 *   uo[0] sine sigma-delta    uo[2]   done flag
 *   uo[1] cosine sigma-delta  uo[7:3] sine level bar (offset binary)
 *
 * Register map (7-bit addr, 8-bit data; ID at 0x7F reads 0xC1):
 *   0x00 CTRL   W: bit0 start, bit1 mode (0 rotate / 1 vector)
 *   0x01 STATUS R: bit0 done (set at op end, cleared by start)
 *   0x02/03 ANGLE_L/H   0x04/05 XIN_L/H     0x06/07 YIN_L/H
 *   0x08/09 COS_L/H (vector: K*magnitude)   0x0A/0B SIN_L/H
 *   0x0C/0D ZOUT_L/H (vector: atan2)
 *   0x10/11 DDS_INC_L/H   0x12 DDS_CTRL (bit0 enable)
 *
 * Copyright (c) 2026 Joonatan Alanampa
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_joonatanalanampa_cordic (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  wire rst = ~rst_n;
  wire standalone = ui_in[7];

  // ---------------------------------------------------------------- SPI
  logic       reg_wr;
  logic [6:0] reg_addr;
  logic [7:0] reg_wdata;
  logic [7:0] reg_rdata;
  logic       miso;

  spi_slave u_spi (
      .clk(clk), .rst_n(rst_n),
      .sclk_i(ui_in[0]), .mosi_i(ui_in[1]), .cs_n_i(ui_in[2]),
      .miso_o(miso),
      .reg_wr(reg_wr), .reg_addr(reg_addr), .reg_wdata(reg_wdata),
      .reg_rdata(reg_rdata)
  );

  assign uio_oe  = 8'b0000_0001;
  assign uio_out = {7'b0, miso};

  // ---------------------------------------------------------------- registers
  logic        mode_r, dds_en_r, done_r;
  logic [15:0] angle_r, xin_r, yin_r, dds_inc_r;
  logic [15:0] cos_r, sin_r, zout_r;
  logic        spi_pend;                    // start requested, op not issued

  // ---------------------------------------------------------------- engine
  logic        eng_start, eng_mode, eng_done;
  logic signed [15:0] eng_cos, eng_sin, eng_zo;
  logic [15:0] eng_zi;
  logic        eng_busy, cur_spi;

  cordic u_cordic (
      .clk(clk), .rst(rst),
      .start(eng_start), .mode(eng_mode),
      .zi(eng_zi), .xi(xin_r), .yi(yin_r),
      .done(eng_done), .cos_o(eng_cos), .sin_o(eng_sin), .zo(eng_zo)
  );

  // ---------------------------------------------------------------- DDS
  logic [23:0] phase;
  wire         dds_en  = standalone | dds_en_r;
  wire [23:0]  dds_inc = standalone ? {7'b0, ui_in[6:0], 10'b0}
                                    : {dds_inc_r, 8'b0};

  // issue: a pending SPI op wins; otherwise free-run the DDS
  wire issue_spi = spi_pend && !eng_busy;
  wire issue_dds = dds_en && !eng_busy && !spi_pend;
  assign eng_start = issue_spi || issue_dds;
  assign eng_mode  = issue_spi ? mode_r : 1'b0;
  assign eng_zi    = issue_spi ? angle_r : phase[23:8];

  always_ff @(posedge clk)
    if (rst) begin
      eng_busy <= 1'b0; cur_spi <= 1'b0; phase <= 24'd0;
    end else begin
      if (eng_start) begin
        eng_busy <= 1'b1;
        cur_spi  <= issue_spi;
        if (issue_dds) phase <= phase + dds_inc;
      end else if (eng_done)
        eng_busy <= 1'b0;
    end

  // DDS sample latch (also freshens the LED bar in standalone)
  logic signed [15:0] sin_s, cos_s;
  always_ff @(posedge clk)
    if (rst) begin
      sin_s <= 16'sd0; cos_s <= 16'sd0;
    end else if (eng_done && !cur_spi) begin
      sin_s <= eng_sin; cos_s <= eng_cos;
    end

  // ---------------------------------------------------------------- reg file
  always_ff @(posedge clk)
    if (rst) begin
      mode_r <= 1'b0; dds_en_r <= 1'b0; done_r <= 1'b0; spi_pend <= 1'b0;
      angle_r <= 16'd0; xin_r <= 16'd0; yin_r <= 16'd0; dds_inc_r <= 16'd0;
      cos_r <= 16'd0; sin_r <= 16'd0; zout_r <= 16'd0;
    end else begin
      if (eng_done && cur_spi) begin
        cos_r  <= eng_cos;
        sin_r  <= eng_sin;
        zout_r <= eng_zo;
        done_r <= 1'b1;
      end
      if (issue_spi) spi_pend <= 1'b0;

      if (reg_wr)
        case (reg_addr)
          7'h00: begin
            if (reg_wdata[0]) begin
              spi_pend <= 1'b1;
              done_r   <= 1'b0;
            end
            mode_r <= reg_wdata[1];
          end
          7'h02: angle_r[7:0]    <= reg_wdata;
          7'h03: angle_r[15:8]   <= reg_wdata;
          7'h04: xin_r[7:0]      <= reg_wdata;
          7'h05: xin_r[15:8]     <= reg_wdata;
          7'h06: yin_r[7:0]      <= reg_wdata;
          7'h07: yin_r[15:8]     <= reg_wdata;
          7'h10: dds_inc_r[7:0]  <= reg_wdata;
          7'h11: dds_inc_r[15:8] <= reg_wdata;
          7'h12: dds_en_r        <= reg_wdata[0];
          default: ;
        endcase
    end

  always_comb
    case (reg_addr)
      7'h00:   reg_rdata = {6'b0, mode_r, 1'b0};
      7'h01:   reg_rdata = {7'b0, done_r};
      7'h02:   reg_rdata = angle_r[7:0];
      7'h03:   reg_rdata = angle_r[15:8];
      7'h04:   reg_rdata = xin_r[7:0];
      7'h05:   reg_rdata = xin_r[15:8];
      7'h06:   reg_rdata = yin_r[7:0];
      7'h07:   reg_rdata = yin_r[15:8];
      7'h08:   reg_rdata = cos_r[7:0];
      7'h09:   reg_rdata = cos_r[15:8];
      7'h0A:   reg_rdata = sin_r[7:0];
      7'h0B:   reg_rdata = sin_r[15:8];
      7'h0C:   reg_rdata = zout_r[7:0];
      7'h0D:   reg_rdata = zout_r[15:8];
      7'h10:   reg_rdata = dds_inc_r[7:0];
      7'h11:   reg_rdata = dds_inc_r[15:8];
      7'h12:   reg_rdata = {7'b0, dds_en_r};
      7'h7F:   reg_rdata = 8'hC1;
      default: reg_rdata = 8'h00;
    endcase

  // ---------------------------------------------------------------- outputs
  // first-order sigma-delta: the carry-out's density IS the sample value
  logic [16:0] sd_sin, sd_cos;
  always_ff @(posedge clk)
    if (rst) begin
      sd_sin <= 17'd0; sd_cos <= 17'd0;
    end else begin
      sd_sin <= {1'b0, sd_sin[15:0]} + {1'b0, sin_s ^ 16'h8000};
      sd_cos <= {1'b0, sd_cos[15:0]} + {1'b0, cos_s ^ 16'h8000};
    end

  assign uo_out = {sin_s[15:11] ^ 5'b10000,   // LED bar, offset binary
                   done_r,
                   sd_cos[16],
                   sd_sin[16]};

  wire _unused = &{ena, uio_in[7:1], 1'b0};

endmodule
