// Here is the counter of the program. Some says he is the best counter in the world.
// It has some special features like:
// - It can jump to an absolute address or a relative address based on the ALU output
// - It can handle interrupts and return from interrupts with the RETI instruction
// - It has a debug jump feature that allows the debugger to set the program counter to any address
// The interrupt jump address is fixed at 0x0002, which is determined by the hardware design. 
// The RETI instruction will return to the address stored in the interrupt address register, 
// which is set when an interrupt occurs. 


module programCounter
  (
    input  wire [15:0] AluIn,
    input  wire        clk,
    input  wire        rst_n,
    input  wire        pc_en,
    input  wire        absJmp,
    input  wire        intr,
    input  wire        reti,

    input  wire [15:0] deb_jump_addr,
    input  wire        deb_jump,
    output wire        deb_jump_ack,

    input  wire        relJmp,
    output wire [15:0] PC,
    output wire [15:0] PCNEXT
  );

  localparam [15:0] interuptFuncAdr = 16'h0002;

  reg [15:0] PCr;
  reg [15:0] interruptAdress;

  assign PC     = PCr;
  assign PCNEXT = PCr + 16'd1;

  assign deb_jump_ack = deb_jump;

  always @(posedge clk or negedge rst_n)
  begin
    if (!rst_n)
    begin
      PCr             <= 16'h0000;
      interruptAdress <= 16'h0000;
    end

    else if (deb_jump)
    begin
      PCr <= deb_jump_addr;
    end

    else if (pc_en)
    begin
      if (reti)
      begin
        PCr <= interruptAdress + 16'd1;
      end

      else if (intr)
      begin
        if (relJmp || absJmp)
          interruptAdress <= PCr - 16'd1;
        else
          interruptAdress <= PCr;

        PCr <= interuptFuncAdr;
      end

      else if (relJmp)
      begin
        PCr <= PCr + AluIn + 16'd1;
      end

      else if (absJmp)
      begin
        PCr <= AluIn;
      end

      else
      begin
        PCr <= PCr + 16'd1;
      end
    end
  end

endmodule
