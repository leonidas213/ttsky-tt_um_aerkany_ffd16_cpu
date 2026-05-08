// Debugger's communicator.
// RX protocol, MSB first:
//   8'hA5 sync + 4-bit cmd + 4-bit addr + 16-bit data = 32 clocks
// The RX side uses a sliding 32-bit window. If one clock is missed or extra,
// it automatically locks again when the next 8'hA5 header appears.
// and after that TX Message is
// 16-bit data, MSB first, on the next 16 dbg_clk falling edges.
//  if it is accepted, the data is 0xACCE.
//  If it is a read command, the data is the register value.
//  If it is a ping command, the data is 0xDB12. Otherwise,
//  the data is 0xEEEE to indicate an error.
module debug_serial_frontend
(
    input  wire        cpu_clk,
    input  wire        rst_n,

    input  wire        dbg_clk,
    input  wire        dbg_data_in,
    output reg         dbg_data_out,
    output reg         dbg_data_oe,

    output reg         reg_wr,
    output reg  [3:0]  reg_addr,
    output reg  [15:0] reg_wdata,
    input  wire [15:0] reg_rdata
);
    localparam S_RX        = 3'd0;
    localparam S_EXEC      = 3'd1;
    localparam S_LOAD_TX   = 3'd2;
    localparam S_TURNAROUND= 3'd3;
    localparam S_TX        = 3'd4;

    localparam SYNC_BYTE  = 8'hA5;

    localparam CMD_PING  = 4'h0;
    localparam CMD_READ  = 4'h1;
    localparam CMD_WRITE = 4'h2;

    reg [2:0]  state;

    reg [2:0]  dbg_clk_sync;
    reg [1:0]  dbg_data_sync;

    wire dbg_clk_rise;
    wire dbg_clk_fall;

    assign dbg_clk_rise = (dbg_clk_sync[2:1] == 2'b01);
    assign dbg_clk_fall = (dbg_clk_sync[2:1] == 2'b10);

    reg [31:0] rx_shift;
    wire [31:0] rx_next;
    wire        rx_next_cmd_valid;
    wire        rx_next_is_frame;

    assign rx_next = {rx_shift[30:0], dbg_data_sync[1]};
    assign rx_next_cmd_valid = (rx_next[23:20] == CMD_PING)  |
                               (rx_next[23:20] == CMD_READ)  |
                               (rx_next[23:20] == CMD_WRITE);
    assign rx_next_is_frame = (rx_next[31:24] == SYNC_BYTE) & rx_next_cmd_valid;

    reg [3:0]  cmd_latched;
    reg [3:0]  addr_latched;
    reg [15:0] data_latched;

    reg [15:0] tx_shift;
    reg [4:0]  tx_count;

    always @(posedge cpu_clk or negedge rst_n) begin
        if (!rst_n) begin
            state        <= S_RX;
            dbg_clk_sync <= 3'b000;
            dbg_data_sync<= 2'b11;
            dbg_data_out <= 1'b1;
            dbg_data_oe  <= 1'b0;
            reg_wr       <= 1'b0;
            reg_addr     <= 4'h0;
            reg_wdata    <= 16'h0000;
            rx_shift     <= 32'h00000000;
            cmd_latched  <= 4'h0;
            addr_latched <= 4'h0;
            data_latched <= 16'h0000;
            tx_shift     <= 16'h0000;
            tx_count     <= 5'd0;
        end else begin
            dbg_clk_sync  <= {dbg_clk_sync[1:0], dbg_clk};
            dbg_data_sync <= {dbg_data_sync[0], dbg_data_in};
            reg_wr <= 1'b0;

            case (state)
                S_RX: begin
                    dbg_data_oe  <= 1'b0;
                    dbg_data_out <= 1'b1;

                    if (dbg_clk_rise) begin
                        if (rx_next_is_frame) begin
                            cmd_latched  <= rx_next[23:20];
                            addr_latched <= rx_next[19:16];
                            data_latched <= rx_next[15:0];
                            rx_shift     <= 32'h00000000;
                            state        <= S_EXEC;
                        end else begin
                            rx_shift <= rx_next;
                        end
                    end
                end

                S_EXEC: begin
                    reg_addr  <= addr_latched;
                    reg_wdata <= data_latched;
                    if (cmd_latched == CMD_WRITE)
                        reg_wr <= 1'b1;
                    state <= S_LOAD_TX;
                end

                S_LOAD_TX: begin
                    if (cmd_latched == CMD_PING)
                        tx_shift <= 16'hDB12;
                    else if (cmd_latched == CMD_READ)
                        tx_shift <= reg_rdata;
                    else if (cmd_latched == CMD_WRITE)
                        tx_shift <= 16'hACCE;
                    else
                        tx_shift <= 16'hEEEE;

                    tx_count     <= 5'd0;
                    dbg_data_oe  <= 1'b0;
                    dbg_data_out <= 1'b1;
                    state        <= S_TURNAROUND;
                end

                S_TURNAROUND: begin
                    dbg_data_oe <= 1'b0;
                    if (dbg_clk_fall) begin
                        dbg_data_oe  <= 1'b1;
                        dbg_data_out <= tx_shift[15];
                        state        <= S_TX;
                    end
                end

                S_TX: begin
                    if (dbg_clk_fall) begin
                        if (tx_count == 5'd15) begin
                            dbg_data_oe  <= 1'b0;
                            dbg_data_out <= 1'b1;
                            rx_shift     <= 32'h00000000;
                            state        <= S_RX;
                        end else begin
                            tx_shift     <= {tx_shift[14:0], 1'b0};
                            dbg_data_out <= tx_shift[14];
                            tx_count     <= tx_count + 5'd1;
                        end
                    end
                end

                default: begin
                    state        <= S_RX;
                    dbg_data_oe  <= 1'b0;
                    dbg_data_out <= 1'b1;
                    rx_shift     <= 32'h00000000;
                end
            endcase
        end
    end

endmodule
