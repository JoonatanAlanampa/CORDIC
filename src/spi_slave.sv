/*
 * SPI slave, mode 0 (CPOL=0, CPHA=0), MSB first.
 *
 * Transaction format (16 bits per CS_n assertion):
 *   byte 0: {rw, addr[6:0]}   rw=1 write, rw=0 read
 *   byte 1: write data (MOSI) or read data (MISO)
 *
 * SCLK/MOSI/CS_n are asynchronous inputs, oversampled with the system
 * clock. Requires SCLK frequency <= clk/10.
 *
 * Copyright (c) 2026 Joonatan Alanampa
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module spi_slave (
    input  logic       clk,
    input  logic       rst_n,

    input  logic       sclk_i,
    input  logic       mosi_i,
    input  logic       cs_n_i,
    output logic       miso_o,

    output logic       reg_wr,     // one-cycle write strobe
    output logic [6:0] reg_addr,   // valid from end of command byte
    output logic [7:0] reg_wdata,
    input  logic [7:0] reg_rdata   // sampled shortly after reg_addr is valid
);

  // 2FF synchronizers (3 stages kept for edge detection)
  logic [2:0] sclk_q;
  logic [2:0] csn_q;
  logic [1:0] mosi_q;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      sclk_q <= '0;
      csn_q  <= 3'b111;
      mosi_q <= '0;
    end else begin
      sclk_q <= {sclk_q[1:0], sclk_i};
      csn_q  <= {csn_q[1:0], cs_n_i};
      mosi_q <= {mosi_q[0], mosi_i};
    end
  end

  wire sclk_rise = (sclk_q[2:1] == 2'b01);
  wire sclk_fall = (sclk_q[2:1] == 2'b10);
  wire cs_active = ~csn_q[1];
  wire cs_start  = (csn_q[2:1] == 2'b10);
  wire mosi_s    = mosi_q[1];

  logic [3:0] bit_cnt;   // 0..15 within the transaction
  logic [6:0] shreg;     // input shift register (7 bits + incoming bit = byte)
  logic       rw_flag;
  logic [7:0] miso_sh;   // output shift register
  logic       load_rd;   // delayed load of read data after address is known

  assign miso_o = miso_sh[7];

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      bit_cnt   <= '0;
      shreg     <= '0;
      rw_flag   <= 1'b0;
      reg_wr    <= 1'b0;
      reg_addr  <= '0;
      reg_wdata <= '0;
      miso_sh   <= '0;
      load_rd   <= 1'b0;
    end else begin
      reg_wr  <= 1'b0;
      load_rd <= 1'b0;

      // Read data becomes valid the cycle after the address is latched;
      // the next SPI edge is many clk cycles away (SCLK <= clk/10).
      if (load_rd)
        miso_sh <= reg_rdata;

      if (cs_start) begin
        bit_cnt <= '0;
        miso_sh <= '0;
      end else if (cs_active && sclk_rise) begin
        shreg   <= {shreg[5:0], mosi_s};
        bit_cnt <= bit_cnt + 4'd1;

        if (bit_cnt == 4'd7) begin
          // command byte complete: {rw, addr}
          rw_flag  <= shreg[6];
          reg_addr <= {shreg[5:0], mosi_s};
          load_rd  <= 1'b1;
        end else if (bit_cnt == 4'd15) begin
          // data byte complete
          reg_wdata <= {shreg[6:0], mosi_s};
          if (rw_flag)
            reg_wr <= 1'b1;
        end
      end else if (cs_active && sclk_fall) begin
        // mode 0 slave shifts out on the falling edge. The 8th falling edge
        // must still present the MSB (loaded after the command byte), so
        // shifting starts at the 9th.
        if (bit_cnt >= 4'd9)
          miso_sh <= {miso_sh[6:0], 1'b0};
      end
    end
  end

endmodule
