// cordic.sv — 16-iteration serial CORDIC engine (shift-add only).
//
// Angle format: 16-bit signed, full turn = 65536 (16384 = 90 deg).
// Rotate mode (mode=0): input angle in zi -> cos_o = cos, sin_o = sin,
//   as signed Q1.15 (32766 ~= +1.0; +/-2 LSB accuracy). Gain K pre-folded.
// Vector mode (mode=1): input point (xi, yi) -> zo = atan2(yi, xi),
//   cos_o = magnitude * 1.6468 (the CORDIC gain; caller divides/documents).
//
// Angles/points outside the right half-plane are folded by a 180-degree
// pre-rotation (angle ^ 0x8000 / point negation) and un-folded at capture.
//
// start is a 1-cycle pulse; 18 cycles later done pulses with results
// valid and held until the next operation.
//
// Copyright (c) 2026 Joonatan Alanampa
// SPDX-License-Identifier: Apache-2.0

`default_nettype none

module cordic (
    input  logic               clk,
    input  logic               rst,

    input  logic               start,
    input  logic               mode,      // 0 = rotate, 1 = vector
    input  logic signed [15:0] zi,        // rotate: target angle
    input  logic signed [15:0] xi,        // vector inputs
    input  logic signed [15:0] yi,

    output logic               done,      // 1-cycle pulse
    output logic signed [15:0] cos_o,     // rotate: cos; vector: K*magnitude
    output logic signed [15:0] sin_o,     // rotate: sin
    output logic signed [15:0] zo         // vector: atan2
);

  // atan(2^-i), with 2 fraction bits of extra precision (65536 = 90 deg
  // internally; the coarse 1x table cost ~11 LSB of sin bias — measured)
  function automatic logic signed [17:0] atan_tab(input logic [3:0] i);
    case (i)
      4'd0:  atan_tab = 18'sd32768;
      4'd1:  atan_tab = 18'sd19344;
      4'd2:  atan_tab = 18'sd10221;
      4'd3:  atan_tab = 18'sd5188;
      4'd4:  atan_tab = 18'sd2604;
      4'd5:  atan_tab = 18'sd1303;
      4'd6:  atan_tab = 18'sd652;
      4'd7:  atan_tab = 18'sd326;
      4'd8:  atan_tab = 18'sd163;
      4'd9:  atan_tab = 18'sd81;
      4'd10: atan_tab = 18'sd41;
      4'd11: atan_tab = 18'sd20;
      4'd12: atan_tab = 18'sd10;
      4'd13: atan_tab = 18'sd5;
      4'd14: atan_tab = 18'sd3;
      default: atan_tab = 18'sd1;
    endcase
  endfunction

  // x, y and z all carry 2 extra fraction bits vs the 16-bit interface:
  // the coarse versions cost ~11 (z) and ~9 (x/y truncation) LSB of error,
  // measured by the exhaustive sweep.
  localparam signed [19:0] X0 = 20'sd79584;   // (K*32767 - margin) << 2

  logic               run, cap, mode_q, fold_q;
  logic [3:0]         i;
  logic signed [19:0] x, y;
  logic signed [18:0] z;

  wire signed [19:0] xs = x >>> i;
  wire signed [19:0] ys = y >>> i;

  // rotate: steer z toward 0; vector: steer y toward 0
  wire ccw = mode_q ? (y < 0) : (z >= 0);

  wire signed [15:0] zfold = zi ^ 16'h8000;
  wire signed [16:0] zr = (z + 19'sd2) >>> 2;   // round back to 16-bit units
  wire signed [17:0] xr = (x + 20'sd2) >>> 2;
  wire signed [17:0] yr = (y + 20'sd2) >>> 2;

  always_ff @(posedge clk)
    if (rst) begin
      run <= 1'b0; cap <= 1'b0; done <= 1'b0;
      mode_q <= 1'b0; fold_q <= 1'b0;
      i <= 4'd0; x <= 20'sd0; y <= 20'sd0; z <= 19'sd0;
      cos_o <= 16'sd0; sin_o <= 16'sd0; zo <= 16'sd0;
    end else begin
      done <= 1'b0;
      cap  <= 1'b0;

      if (start) begin
        mode_q <= mode;
        i      <= 4'd0;
        run    <= 1'b1;
        if (mode) begin                    // vector: fold left half-plane
          fold_q <= xi[15];
          x <= xi[15] ? -{{2{xi[15]}}, xi, 2'b00} : {{2{xi[15]}}, xi, 2'b00};
          y <= xi[15] ? -{{2{yi[15]}}, yi, 2'b00} : {{2{yi[15]}}, yi, 2'b00};
          z <= 19'sd0;
        end else begin                     // rotate: fold |angle| > 90 deg
          fold_q <= zi[15] ^ zi[14];
          x <= X0;
          y <= 20'sd0;
          z <= (zi[15] ^ zi[14]) ? {zfold[15], zfold, 2'b00}
                                 : {zi[15], zi, 2'b00};
        end
      end else if (run) begin
        if (ccw) begin
          x <= x - ys;
          y <= y + xs;
          z <= z - atan_tab(i);
        end else begin
          x <= x + ys;
          y <= y - xs;
          z <= z + atan_tab(i);
        end
        i <= i + 4'd1;
        if (i == 4'd15) begin
          run <= 1'b0;
          cap <= 1'b1;                     // final values land next cycle
        end
      end else if (cap) begin              // capture, applying the un-fold
        cos_o <= (fold_q && !mode_q) ? -xr[15:0] : xr[15:0];
        sin_o <= (fold_q && !mode_q) ? -yr[15:0] : yr[15:0];
        zo    <= fold_q ? (zr[15:0] ^ 16'h8000) : zr[15:0];
        done  <= 1'b1;
      end
    end

endmodule
