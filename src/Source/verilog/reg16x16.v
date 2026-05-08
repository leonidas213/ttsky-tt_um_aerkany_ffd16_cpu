module RegisterBlock (
    input  [15:0] DataIn,
    input         WE,
    input         clk,
    input  [3:0]  src,
    input  [3:0]  Dest,
    output [15:0] RDest,
    output [15:0] Rsrc
  );

  reg [15:0] regs [0:15];

  always @(negedge clk )
  begin

    if (WE)
    begin
      regs[Dest] <= DataIn;
    end
  end

  // read ports
  assign Rsrc  = regs[src];
  assign RDest = regs[Dest];

endmodule
