`ifndef VERILATOR
module testbench;
  reg [4095:0] vcdfile;
  reg clock;
`else
module testbench(input clock, output reg genclock);
  initial genclock = 1;
`endif
  reg genclock = 1;
  reg [31:0] cycle = 0;
  reg [0:0] PI_start;
  wire [0:0] PI_clk = clock;
  reg [0:0] PI_mode;
  reg [15:0] PI_yi;
  reg [15:0] PI_xi;
  reg [15:0] PI_zi;
  f_top UUT (
    .start(PI_start),
    .clk(PI_clk),
    .mode(PI_mode),
    .yi(PI_yi),
    .xi(PI_xi),
    .zi(PI_zi)
  );
`ifndef VERILATOR
  initial begin
    if ($value$plusargs("vcd=%s", vcdfile)) begin
      $dumpfile(vcdfile);
      $dumpvars(0, testbench);
    end
    #5 clock = 0;
    while (genclock) begin
      #5 clock = 0;
      #5 clock = 1;
    end
  end
`endif
  initial begin
`ifndef VERILATOR
    #1;
`endif
    // UUT.dut.$auto$async2sync.\cc:107:execute$505  = 1'b0;
    // UUT.dut.$auto$async2sync.\cc:116:execute$503  = 1'b1;
    // UUT.dut.$auto$async2sync.\cc:116:execute$509  = 1'b1;
    UUT.dut.ccw = 1'b0;
    UUT.dut.cos_o = 16'b0000000000000000;
    UUT.dut.cx = 1'b0;
    UUT.dut.cy = 1'b0;
    UUT.dut.cz = 1'b0;
    UUT.dut.done = 1'b1;
    UUT.dut.fold_q = 1'b0;
    UUT.dut.i = 4'b0000;
    UUT.dut.k = 5'b00000;
    UUT.dut.mode_q = 1'b0;
    UUT.dut.sin_o = 16'b0000000000000000;
    UUT.dut.st = 2'b00;
    UUT.dut.x = 20'b00000000000000000000;
    UUT.dut.xsgn = 1'b0;
    UUT.dut.y = 20'b00000000000000000000;
    UUT.dut.ysgn = 1'b0;
    UUT.dut.z = 20'b00000000000000000000;
    UUT.dut.zo = 16'b0000000000000000;
    UUT.f_rst = 1'b1;
    UUT.dut.$auto$proc_rom.\cc:155:do_switch$130 [4'b0000] = 18'b001000000000000000;

    // state 0
    PI_start = 1'b0;
    PI_mode = 1'b0;
    PI_yi = 16'b0000000000000000;
    PI_xi = 16'b0000000000000000;
    PI_zi = 16'b0000000000000000;
  end
  always @(posedge clock) begin
    // state 1
    if (cycle == 0) begin
      PI_start <= 1'b0;
      PI_mode <= 1'b0;
      PI_yi <= 16'b0000000000000000;
      PI_xi <= 16'b0000000000000000;
      PI_zi <= 16'b0000000000000000;
    end

    genclock <= cycle < 1;
    cycle <= cycle + 1;
  end
endmodule
