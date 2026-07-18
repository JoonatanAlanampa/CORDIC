// f_top.sv — formal top: reset for one cycle, then every input free.
// The solver drives start/mode/zi/xi/yi with full adversarial freedom.
`default_nettype none

module f_top (
    input wire               clk,
    input wire               start,
    input wire               mode,
    input wire signed [15:0] zi,
    input wire signed [15:0] xi,
    input wire signed [15:0] yi
);

  reg f_rst = 1'b1;
  always @(posedge clk) f_rst <= 1'b0;

  cordic dut (
      .clk(clk), .rst(f_rst),
      .start(start), .mode(mode),
      .zi(zi), .xi(xi), .yi(yi),
      .done(), .cos_o(), .sin_o(), .zo()
  );

endmodule
