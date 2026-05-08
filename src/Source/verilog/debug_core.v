// Debugger's core logic.
// it can
// - set breakpoint(only 1 at the moment)
// - halt and run the CPU
// - single step the CPU
// - load a new PC value into the CPU to jump to an arbitrary location (useful for stepping through reset/startup code that is not easily reachable with a breakpoint)
// - static break on BRK instruction (compiled into the code) (useful for catching infinite loops in startup code)
// It also provides a register interface for the debugger to read CPU status and control the debug features.
// - Program counter, instruction register, and flags are readable for debugging purposes.
//
module debug_core
  (
    input  wire        clk,
    input  wire        rst_n,

    // Register port
    input  wire        reg_wr,
    input  wire [3:0]  reg_addr,
    input  wire [15:0] reg_wdata,
    output reg  [15:0] reg_rdata,

    // CPU status
    input  wire        cpu_dbg_halted,
    input  wire [2:0]  cpu_flags,
    input  wire [15:0] cpu_pc,
    input  wire [15:0] cpu_ir,
    input  wire        instr_is_brk,
    input  wire        execute_now_pulse,

    // Debug control outputs
    output reg         dbg_enable,
    output reg         dbg_halt_req,
    output reg         dbg_run_req,
    output reg         dbg_step_req,
    output reg         static_break_enable,

    output wire        dbg_break_hit,
    output wire        dbg_break_after_exec,

    // Debug load-PC request.
    // dbg_jump_req is sticky and stays high until dbg_jump_ack is seen.
    output reg         dbg_jump_req,
    output reg  [15:0] dbg_jump_addr,
    input  wire        dbg_jump_ack
  );

  localparam REG_ID        = 4'h0;
  localparam REG_STATUS    = 4'h1;
  localparam REG_CONTROL   = 4'h2;
  localparam REG_FLAGS     = 4'h3;
  localparam REG_PC        = 4'h4;
  localparam REG_IR        = 4'h5;
  localparam REG_BP0       = 4'h6;
  localparam REG_BPCTRL    = 4'h7;
  localparam REG_JUMP_ADDR = 4'h8;

  // REG_CONTROL bits, write side:
  //   bit0 = debug enable level
  //   bit1 = halt request level/set
  //   bit2 = run pulse
  //   bit3 = step pulse
  //   bit4 = reserved
  //   bit5 = static BRK enable level
  //   bit6 = jump/load-PC request using REG_JUMP_ADDR

  // One dynamic breakpoint only sadly
  reg  [15:0] bp0;
  reg         bp_enable;
  reg         bp_resume_mask;
  wire        resume_cmd;
  wire        bp_raw_hit;

  assign resume_cmd = dbg_run_req | dbg_step_req;
  assign bp_raw_hit = dbg_enable & bp_enable & (cpu_pc == bp0);

  assign dbg_break_hit        = bp_raw_hit & ~bp_resume_mask;
  assign dbg_break_after_exec = dbg_enable & static_break_enable & instr_is_brk;

  always @(posedge clk or negedge rst_n)
  begin
    if (!rst_n)
    begin
      dbg_enable           <= 1'b0;
      dbg_halt_req         <= 1'b0;
      dbg_run_req          <= 1'b0;
      dbg_step_req         <= 1'b0;
      static_break_enable  <= 1'b0;
      dbg_jump_req         <= 1'b0;
      dbg_jump_addr        <= 16'h0000;
      bp0                  <= 16'h0000;
      bp_enable            <= 1'b0;
    end
    else
    begin
      dbg_run_req  <= 1'b0;
      dbg_step_req <= 1'b0;
      if (dbg_jump_ack)
        dbg_jump_req <= 1'b0;

      if (cpu_dbg_halted)
        dbg_halt_req <= 1'b0;

      if (reg_wr)
      begin
        case (reg_addr)
          REG_CONTROL:
          begin
            dbg_enable          <= reg_wdata[0];
            static_break_enable <= reg_wdata[5];

            if (!reg_wdata[0])
            begin
              dbg_halt_req <= 1'b0;
              dbg_jump_req <= 1'b0;
            end

            if (reg_wdata[1] && reg_wdata[0])
              dbg_halt_req <= 1'b1;

            if (reg_wdata[2] && reg_wdata[0])
            begin
              dbg_run_req  <= 1'b1;
              dbg_halt_req <= 1'b0;
            end

            if (reg_wdata[3] && reg_wdata[0])
            begin
              dbg_step_req <= 1'b1;
              dbg_halt_req <= 1'b0;
            end

            if (reg_wdata[6] && reg_wdata[0])
              dbg_jump_req <= 1'b1;
          end

          REG_BP0:
            bp0 <= reg_wdata;

          REG_BPCTRL:
            bp_enable <= reg_wdata[0];

          REG_JUMP_ADDR:
            dbg_jump_addr <= reg_wdata;

          default:
          begin
          end
        endcase
      end
    end
  end

  always @(*)
  begin
    case (reg_addr)
      REG_ID:
        reg_rdata = 16'hDB11;

      REG_STATUS:
        reg_rdata = {
          8'h00,
          bp_resume_mask,
          bp_enable,
          static_break_enable,
          dbg_enable,
          cpu_dbg_halted,
          1'b0,          // reserved
          dbg_jump_req,  // pending jump/load-PC request
          dbg_halt_req
        };

      REG_CONTROL:
        reg_rdata = {
          9'h000,
          dbg_jump_req,          // bit6: pending jump state
          static_break_enable,   // bit5
          1'b0,                  // bit4 reserved
          1'b0,                  // bit3 step is write-only pulse
          1'b0,                  // bit2 run is write-only pulse
          dbg_halt_req,          // bit1
          dbg_enable             // bit0
        };

      REG_FLAGS:
        reg_rdata = {13'h0000, cpu_flags};

      REG_PC:
        reg_rdata = cpu_pc;

      REG_IR:
        reg_rdata = cpu_ir;

      REG_BP0:
        reg_rdata = bp0;

      REG_BPCTRL:
        reg_rdata = {15'h0000, bp_enable};

      REG_JUMP_ADDR:
        reg_rdata = dbg_jump_addr;

      default:
        reg_rdata = 16'h0000;
    endcase
  end

  always @(posedge clk or negedge rst_n)
  begin
    if (!rst_n)
      bp_resume_mask <= 1'b0;
    else if (execute_now_pulse)
      bp_resume_mask <= 1'b0;
    else if (cpu_dbg_halted & resume_cmd)
      bp_resume_mask <= 1'b1;
  end

endmodule
