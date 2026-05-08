// this module controlles the execute timing of the CPU.
// The debugger can interface with this module to alter the execution flow (halt, step, etc).
// if a data needs to be loaded or stored, the controller will wait for the data_done signal 
// before proceeding to the next instruction fetch.

module cpu_cycle_controller
(
    input  wire clk,
    input  wire rst_n,

    input  wire fetch_done,
    input  wire data_done,

    input  wire ld,
    input  wire st,
    input  wire flash_ld,

    input  wire dbg_enable,
    input  wire dbg_halt_req,
    input  wire dbg_run_req,
    input  wire dbg_step_req,
    input  wire dbg_break_hit,
    input  wire dbg_break_after_exec,

    output wire fetch_req,
    output wire execute_now_pulse,
    output wire dbg_halted
);

  localparam S_REQ_FETCH  = 3'd0;
  localparam S_WAIT_FETCH = 3'd1;
  localparam S_EXECUTE    = 3'd2;
  localparam S_WAIT_DATA  = 3'd3;
  localparam S_HALTED     = 3'd4;

  reg [2:0] state;
  reg       step_active;

  wire mem_op;
  wire stop_after_exec;

  assign mem_op            = ld | st | flash_ld;
  assign fetch_req         = (state == S_REQ_FETCH);
  assign execute_now_pulse = (state == S_EXECUTE);
  assign dbg_halted        = (state == S_HALTED);
  assign stop_after_exec   = dbg_enable & (dbg_halt_req | step_active | dbg_break_after_exec);

  always @(posedge clk or negedge rst_n)
  begin
    if (!rst_n)
    begin
      state       <= S_REQ_FETCH;
      step_active <= 1'b0;
    end
    else if (!dbg_enable)
    begin
      step_active <= 1'b0;

      case (state)
        S_REQ_FETCH:  state <= S_WAIT_FETCH;
        S_WAIT_FETCH: if (fetch_done) state <= S_EXECUTE;
        S_EXECUTE:    state <= mem_op ? S_WAIT_DATA : S_REQ_FETCH;
        S_WAIT_DATA:  if (data_done) state <= S_REQ_FETCH;
        default:      state <= S_REQ_FETCH;
      endcase
    end
    else
    begin
      case (state)
        S_REQ_FETCH:
        begin
          if (dbg_halt_req)
          begin
            state       <= S_HALTED;
            step_active <= 1'b0;
          end
          else
            state <= S_WAIT_FETCH;
        end

        S_WAIT_FETCH:
        begin
          if (fetch_done)
          begin
            if (dbg_break_hit | dbg_halt_req)
            begin
              state       <= S_HALTED;
              step_active <= 1'b0;
            end
            else
              state <= S_EXECUTE;
          end
        end

        S_EXECUTE:
        begin
          if (mem_op)
            state <= S_WAIT_DATA;
          else if (stop_after_exec)
          begin
            state       <= S_HALTED;
            step_active <= 1'b0;
          end
          else
            state <= S_REQ_FETCH;
        end

        S_WAIT_DATA:
        begin
          if (data_done)
          begin
            if (stop_after_exec)
            begin
              state       <= S_HALTED;
              step_active <= 1'b0;
            end
            else
              state <= S_REQ_FETCH;
          end
        end

        S_HALTED:
        begin
          if (dbg_run_req)
          begin
            state       <= S_REQ_FETCH;
            step_active <= 1'b0;
          end
          else if (dbg_step_req)
          begin
            state       <= S_REQ_FETCH;
            step_active <= 1'b1;
          end
        end

        default:
        begin
          state       <= S_REQ_FETCH;
          step_active <= 1'b0;
        end
      endcase
    end
  end

endmodule
