module debug_panel_serial_sim
(
    input  wire        clk,
    input  wire        rst_n,
    input  wire        btn_dbg_toggle,
    input  wire        btn_static_break_toggle,
    input  wire        btn_halt,
    input  wire        btn_run,
    input  wire        btn_step,
    input  wire        btn_soft_reset,
    input  wire        btn_jump,
    input  wire        btn_write,
    input  wire        btn_read,
    input  wire        btn_ping,
    input  wire [3:0]  sw_addr,
    input  wire [15:0] sw_wdata,
    output reg         dbg_clk,
    output reg         dbg_data_out,
    output reg         dbg_data_oe,
    input  wire        dbg_data_in,
    output reg  [15:0] live_rdata,
    output reg  [15:0] last_response,
    output reg         busy,
    output reg         dbg_enable_state,
    output reg         static_break_enable_state
);
    localparam CLKDIV = 4;

    // New debugger frontend protocol:
    //   MSB first, 32 clocks total
    //   8'hA5 sync + 4-bit cmd + 4-bit addr + 16-bit data
    localparam SYNC_BYTE   = 8'hA5;
    localparam REG_CONTROL = 4'h2;
    // Write sw_wdata here when btn_jump is pressed.
    // Change this address if your debugger backend uses another jump register.
    localparam REG_JUMP    = 4'h3;

    localparam CMD_PING  = 4'h0;
    localparam CMD_READ  = 4'h1;
    localparam CMD_WRITE = 4'h2;

    localparam S_IDLE       = 3'd0;
    localparam S_CMD_RISE   = 3'd1;
    localparam S_CMD_FALL   = 3'd2;
    localparam S_TURNAROUND = 3'd3;
    localparam S_RESP_RISE  = 3'd4;
    localparam S_RESP_FALL  = 3'd5;
    localparam S_DONE       = 3'd6;

    reg [2:0] state;
    reg btn_dbg_toggle_d, btn_static_break_toggle_d;
    reg btn_halt_d, btn_run_d, btn_step_d, btn_soft_reset_d, btn_jump_d;
    reg btn_write_d, btn_read_d, btn_ping_d;

    wire p_dbg_toggle    = btn_dbg_toggle          & ~btn_dbg_toggle_d;
    wire p_static_toggle = btn_static_break_toggle & ~btn_static_break_toggle_d;
    wire p_halt          = btn_halt                & ~btn_halt_d;
    wire p_run           = btn_run                 & ~btn_run_d;
    wire p_step          = btn_step                & ~btn_step_d;
    wire p_soft_reset    = btn_soft_reset          & ~btn_soft_reset_d;
    wire p_jump          = btn_jump                & ~btn_jump_d;
    wire p_write         = btn_write               & ~btn_write_d;
    wire p_read          = btn_read                & ~btn_read_d;
    wire p_ping          = btn_ping                & ~btn_ping_d;

    wire next_dbg_enable_state          = dbg_enable_state ^ p_dbg_toggle;
    wire next_static_break_enable_state = static_break_enable_state ^ p_static_toggle;

    wire control_write_event = p_dbg_toggle | p_static_toggle | p_halt | p_run | p_step | p_soft_reset;

    // Control register write payload:
    // [0] dbg_enable level
    // [1] halt pulse
    // [2] run pulse
    // [3] step pulse
    // [4] soft_reset pulse
    // [5] static_break_enable level
    // [15:6] zero
    wire [15:0] control_word = {
        10'h000,
        next_static_break_enable_state,
        p_soft_reset,
        p_step,
        p_run,
        p_halt,
        next_dbg_enable_state
    };

    reg [31:0] cmd_shift;
    reg [5:0]  cmd_bits_left;
    reg [15:0] resp_shift;
    reg [4:0]  resp_bits_left;
    reg [31:0] pending_word;
    reg        pending_valid;
    reg [15:0] clkdiv_cnt;
    reg [3:0]  pending_cmd;

    wire tick = (clkdiv_cnt == (CLKDIV-1));

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= S_IDLE;
            btn_dbg_toggle_d <= 1'b0;
            btn_static_break_toggle_d <= 1'b0;
            btn_halt_d <= 1'b0;
            btn_run_d <= 1'b0;
            btn_step_d <= 1'b0;
            btn_soft_reset_d <= 1'b0;
            btn_jump_d <= 1'b0;
            btn_write_d <= 1'b0;
            btn_read_d <= 1'b0;
            btn_ping_d <= 1'b0;
            dbg_clk <= 1'b0;
            dbg_data_out <= 1'b1;
            dbg_data_oe <= 1'b0;
            live_rdata <= 16'h0000;
            last_response <= 16'h0000;
            busy <= 1'b0;
            dbg_enable_state <= 1'b0;
            static_break_enable_state <= 1'b0;
            cmd_shift <= 32'h00000000;
            cmd_bits_left <= 6'd0;
            resp_shift <= 16'h0000;
            resp_bits_left <= 5'd0;
            pending_word <= 32'h00000000;
            pending_valid <= 1'b0;
            pending_cmd <= 4'h0;
            clkdiv_cnt <= 16'h0000;
        end else begin
            btn_dbg_toggle_d <= btn_dbg_toggle;
            btn_static_break_toggle_d <= btn_static_break_toggle;
            btn_halt_d <= btn_halt;
            btn_run_d <= btn_run;
            btn_step_d <= btn_step;
            btn_soft_reset_d <= btn_soft_reset;
            btn_jump_d <= btn_jump;
            btn_write_d <= btn_write;
            btn_read_d <= btn_read;
            btn_ping_d <= btn_ping;

            if (tick)
                clkdiv_cnt <= 16'h0000;
            else
                clkdiv_cnt <= clkdiv_cnt + 16'h0001;

            if (p_dbg_toggle)
                dbg_enable_state <= next_dbg_enable_state;
            if (p_static_toggle)
                static_break_enable_state <= next_static_break_enable_state;

            if (!pending_valid && !busy) begin
                if (control_write_event) begin
                    pending_word  <= {SYNC_BYTE, CMD_WRITE, REG_CONTROL, control_word};
                    pending_cmd   <= CMD_WRITE;
                    pending_valid <= 1'b1;
                end else if (p_jump) begin
                    pending_word  <= {SYNC_BYTE, CMD_WRITE, REG_JUMP, sw_wdata};
                    pending_cmd   <= CMD_WRITE;
                    pending_valid <= 1'b1;
                end else if (p_write) begin
                    pending_word  <= {SYNC_BYTE, CMD_WRITE, sw_addr, sw_wdata};
                    pending_cmd   <= CMD_WRITE;
                    pending_valid <= 1'b1;
                end else if (p_read) begin
                    pending_word  <= {SYNC_BYTE, CMD_READ, sw_addr, 16'h0000};
                    pending_cmd   <= CMD_READ;
                    pending_valid <= 1'b1;
                end else if (p_ping) begin
                    pending_word  <= {SYNC_BYTE, CMD_PING, 4'h0, 16'h0000};
                    pending_cmd   <= CMD_PING;
                    pending_valid <= 1'b1;
                end
            end

            if (tick) begin
                case (state)
                    S_IDLE: begin
                        dbg_clk <= 1'b0;
                        dbg_data_out <= 1'b1;
                        if (pending_valid) begin
                            busy <= 1'b1;
                            dbg_data_oe <= 1'b1;
                            cmd_shift <= pending_word;
                            cmd_bits_left <= 6'd32;
                            dbg_data_out <= pending_word[31];
                            resp_shift <= 16'h0000;
                            resp_bits_left <= 5'd16;
                            pending_valid <= 1'b0;
                            state <= S_CMD_RISE;
                        end else begin
                            dbg_data_oe <= 1'b0;
                            busy <= 1'b0;
                        end
                    end

                    S_CMD_RISE: begin
                        dbg_clk <= 1'b1;
                        state <= S_CMD_FALL;
                    end

                    S_CMD_FALL: begin
                        dbg_clk <= 1'b0;
                        if (cmd_bits_left == 6'd1) begin
                            dbg_data_oe <= 1'b0;
                            dbg_data_out <= 1'b1;
                            state <= S_TURNAROUND;
                        end else begin
                            cmd_shift <= {cmd_shift[30:0], 1'b0};
                            cmd_bits_left <= cmd_bits_left - 6'd1;
                            dbg_data_out <= cmd_shift[30];
                            state <= S_CMD_RISE;
                        end
                    end

                    S_TURNAROUND: begin
                        // Keep the bus released for one divided clock period.
                        // The frontend drives the first response bit after seeing a dbg_clk falling edge.
                        dbg_clk <= 1'b0;
                        dbg_data_oe <= 1'b0;
                        dbg_data_out <= 1'b1;
                        state <= S_RESP_RISE;
                    end

                    S_RESP_RISE: begin
                        dbg_clk <= 1'b1;
                        resp_shift <= {resp_shift[14:0], dbg_data_in};
                        state <= S_RESP_FALL;
                    end

                    S_RESP_FALL: begin
                        dbg_clk <= 1'b0;
                        if (resp_bits_left == 5'd1) begin
                            // Include the bit sampled during the immediately preceding S_RESP_RISE.
                            last_response <= resp_shift;
                            if (pending_cmd == CMD_READ)
                                live_rdata <= resp_shift;
                            state <= S_DONE;
                        end else begin
                            resp_bits_left <= resp_bits_left - 5'd1;
                            state <= S_RESP_RISE;
                        end
                    end

                    S_DONE: begin
                        dbg_clk <= 1'b0;
                        dbg_data_oe <= 1'b0;
                        dbg_data_out <= 1'b1;
                        busy <= 1'b0;
                        state <= S_IDLE;
                    end

                    default: begin
                        dbg_clk <= 1'b0;
                        dbg_data_oe <= 1'b0;
                        dbg_data_out <= 1'b1;
                        busy <= 1'b0;
                        state <= S_IDLE;
                    end
                endcase
            end
        end
    end
endmodule
