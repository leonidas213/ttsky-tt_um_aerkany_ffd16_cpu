// Flat / no-instantiation memory interface.
// Area-focused version: Flash = QSPI continuous read, RAM = plain SPI read/write.
//
// Main area reductions versus initwait version:
//   - no 24-bit runtime address shift register
//   - no 16-bit runtime write-data shift register
//   - no 8-bit RAM command shift register
//   - no 8-bit flash mode shift register
//   - smaller state/counter registers
//   - smaller init wait counter for 50 MHz / 40 ms max default wait
//   - RAM reset/init removed to save area; RAM CS stays high during init
//
// CPU side:
//   spi_target = 0 -> Flash read only, byte address {7'b0, addr, 1'b0}
//   spi_target = 1 -> RAM read/write, byte address {1'b0, 6'b0, addr, 1'b0}
//
// External bus pins:
//   Flash QSPI uses IO[3:0].
//   RAM SPI uses IO0 = MOSI and IO1 = MISO. IO2/IO3 are released for RAM.
// 

module qspi_memory_interface (
    input  wire        clk,
    input  wire        spi_rst_n,

    input  wire        st,
    input  wire        ld,
    input  wire        spi_target,    // 0 = flash, 1 = RAM
    input  wire [15:0] addr,
    input  wire [15:0] data_in,
    output reg  [15:0] data_out,

    output wire        spi_clk,
    output wire        spi_flash_cs,  // active low
    output wire        spi_ram_cs,    // active low

    input  wire [3:0]  spi_data_in,
    output wire [3:0]  spi_data_out,
    output wire [3:0]  spi_data_oe,

    output reg         busy
);

// ============================================================
// 0) Shared output mux: init owns pins until init_done = 1
// ============================================================

    wire init_done;

    reg        init_spi_clk;
    reg        init_flash_cs;
    reg        init_ram_cs;
    reg [3:0]  init_data_out;
    reg [3:0]  init_data_oe;

    reg        core_spi_clk;
    reg        core_flash_cs;
    reg        core_ram_cs;
    reg [3:0]  core_data_out;
    reg [3:0]  core_data_oe;

    assign spi_clk      = init_done ? core_spi_clk   : init_spi_clk;
    assign spi_flash_cs = init_done ? core_flash_cs  : init_flash_cs;
    assign spi_ram_cs   = init_done ? core_ram_cs    : init_ram_cs;
    assign spi_data_out = init_done ? core_data_out  : init_data_out;
    assign spi_data_oe  = init_done ? core_data_oe   : init_data_oe;

// ============================================================
// 1) CPU 16-bit word wrapper FSM
// ============================================================

    localparam W_IDLE       = 2'd0;
    localparam W_START      = 2'd1;
    localparam W_WAIT_BUSY  = 2'd2;
    localparam W_WAIT_IDLE  = 2'd3;

    reg [1:0]  wstate;
    reg        op_is_read;
    reg [15:0] core_addr_cpu;
    reg [15:0] core_write_word;
    reg        core_start_read;
    reg        core_start_write;
    reg        core_target_ram;

    wire [15:0] core_read_word;
    wire        core_busy;

    always @(posedge clk or negedge spi_rst_n) begin
        if (!spi_rst_n) begin
            wstate           <= W_IDLE;
            busy             <= 1'b0;
            op_is_read       <= 1'b0;
            core_addr_cpu    <= 16'h0000;
            core_write_word  <= 16'h0000;
            core_start_read  <= 1'b0;
            core_start_write <= 1'b0;
            core_target_ram  <= 1'b0;
            data_out         <= 16'h0000;
        end else begin
            core_start_read  <= 1'b0;
            core_start_write <= 1'b0;

            case (wstate)
                W_IDLE: begin
                    busy <= !init_done;

                    if (!init_done) begin
                        wstate <= W_IDLE;
                    end else if (ld) begin
                        busy            <= 1'b1;
                        op_is_read      <= 1'b1;
                        core_target_ram <= spi_target;
                        core_addr_cpu   <= addr;
                        wstate          <= W_START;
                    end else if (st) begin
                        // Flash writing is intentionally blocked here.
                        // RAM writes are SPI only.
                        if (spi_target) begin
                            busy             <= 1'b1;
                            op_is_read       <= 1'b0;
                            core_target_ram  <= 1'b1;
                            core_addr_cpu    <= addr;
                            core_write_word  <= data_in;
                            wstate           <= W_START;
                        end else begin
                            busy   <= 1'b0;
                            wstate <= W_IDLE;
                        end
                    end
                end

                W_START: begin
                    busy <= 1'b1;
                    if (op_is_read)
                        core_start_read <= 1'b1;
                    else
                        core_start_write <= 1'b1;
                    wstate <= W_WAIT_BUSY;
                end

                W_WAIT_BUSY: begin
                    busy <= 1'b1;
                    if (core_busy)
                        wstate <= W_WAIT_IDLE;
                end

                W_WAIT_IDLE: begin
                    if (!core_busy) begin
                        if (op_is_read)
                            data_out <= core_read_word;
                        busy       <= 1'b0;
                        op_is_read <= 1'b0;
                        wstate     <= W_IDLE;
                    end else begin
                        busy <= 1'b1;
                    end
                end
            endcase
        end
    end

// ============================================================
// 2) Startup initializer FSM
// ============================================================

    localparam I_IDLE       = 3'd0;
    localparam I_WAIT_PWR   = 3'd1;
    localparam I_LOAD       = 3'd2;
    localparam I_SHIFT_LOW  = 3'd3;
    localparam I_SHIFT_HIGH = 3'd4;
    localparam I_CS_HIGH    = 3'd5;
    localparam I_GAP        = 3'd6;
    localparam I_DONE       = 3'd7;

    localparam INIT_STEP_FLASH_RST_EN = 4'd0;
    localparam INIT_STEP_FLASH_RST    = 4'd1;
    localparam INIT_STEP_FLASH_WREN   = 4'd2;
    localparam INIT_STEP_FLASH_SR2    = 4'd3;
    localparam INIT_STEP_FLASH_EB     = 4'd4;
    localparam INIT_STEP_FLASH_CONT   = 4'd5;
    localparam INIT_STEP_END          = 4'd6;

    // Default waits fit in 22 bits at 50 MHz:
    // 40 ms = 2,000,000 cycles. If you increase INIT_CLK_HZ a lot,
    // increase INIT_WAIT_BITS too.
    localparam integer INIT_CLK_HZ      = 50000000;
    localparam integer INIT_WAIT_BITS   = 22;
`ifdef COCOTB_SIM_FAST_INIT
    localparam [INIT_WAIT_BITS-1:0] INIT_POWER_WAIT_CYCLES      = 22'd82;
    localparam [INIT_WAIT_BITS-1:0] INIT_RESET_WAIT_CYCLES      = 22'd82;
    localparam [INIT_WAIT_BITS-1:0] INIT_FLASH_SR2_WAIT_CYCLES  = 22'd82;
    localparam [INIT_WAIT_BITS-1:0] INIT_FLASH_CONT_WAIT_CYCLES = 22'd82;
    localparam [INIT_WAIT_BITS-1:0] INIT_CMD_GAP_CYCLES         = 22'd82;
`else
    localparam [INIT_WAIT_BITS-1:0] INIT_POWER_WAIT_CYCLES      = (INIT_CLK_HZ / 1000) * 10;
    localparam [INIT_WAIT_BITS-1:0] INIT_RESET_WAIT_CYCLES      = (INIT_CLK_HZ / 1000) * 2;
    localparam [INIT_WAIT_BITS-1:0] INIT_FLASH_SR2_WAIT_CYCLES  = (INIT_CLK_HZ / 1000) * 40;
    localparam [INIT_WAIT_BITS-1:0] INIT_FLASH_CONT_WAIT_CYCLES = (INIT_CLK_HZ / 1000) * 1;
    localparam [INIT_WAIT_BITS-1:0] INIT_CMD_GAP_CYCLES         = (INIT_CLK_HZ / 1000000) * 5 + 4;
`endif

    function [INIT_WAIT_BITS-1:0] init_gap_cycles;
        input [3:0] stp;
        begin
            case (stp)
                INIT_STEP_FLASH_RST:  init_gap_cycles = INIT_RESET_WAIT_CYCLES;
                INIT_STEP_FLASH_SR2:  init_gap_cycles = INIT_FLASH_SR2_WAIT_CYCLES;
                INIT_STEP_FLASH_CONT: init_gap_cycles = INIT_FLASH_CONT_WAIT_CYCLES;
                default:              init_gap_cycles = INIT_CMD_GAP_CYCLES;
            endcase
        end
    endfunction

    function [2:0] init_bytes_left;
        input [3:0] stp;
        begin
            case (stp)
                INIT_STEP_FLASH_SR2:  init_bytes_left = 3'd2;
                INIT_STEP_FLASH_CONT: init_bytes_left = 3'd6;
                INIT_STEP_END:        init_bytes_left = 3'd0;
                default:              init_bytes_left = 3'd1;
            endcase
        end
    endfunction

    function [7:0] init_byte;
        input [3:0] stp;
        input [2:0] idx;
        begin
            case (stp)
                INIT_STEP_FLASH_RST_EN: init_byte = 8'h66;
                INIT_STEP_FLASH_RST:    init_byte = 8'h99;
                INIT_STEP_FLASH_WREN:   init_byte = 8'h06;
                INIT_STEP_FLASH_SR2:    init_byte = (idx == 3'd0) ? 8'h31 : 8'h02;
                INIT_STEP_FLASH_EB:     init_byte = 8'hEB;
                INIT_STEP_FLASH_CONT: begin
                    case (idx)
                        3'd0: init_byte = 8'h00; // addr[23:16]
                        3'd1: init_byte = 8'h00; // addr[15:8]
                        3'd2: init_byte = 8'h00; // addr[7:0]
                        3'd3: init_byte = 8'hA0; // continuous-read mode bits
                        default: init_byte = 8'h00; // dummy clocks
                    endcase
                end
                default: init_byte = 8'h00;
            endcase
        end
    endfunction

    reg [2:0]  init_state;
    reg [3:0]  init_step;
    reg [7:0]  init_shift;
    reg [2:0]  init_bit_cnt;
    reg [INIT_WAIT_BITS-1:0] init_wait_cnt;
    reg [2:0]  init_byte_idx;
    reg        init_done_r;

    wire       init_use_quad_w   = (init_step == INIT_STEP_FLASH_CONT);
    wire [2:0] init_bytes_left_w = init_bytes_left(init_step);

    assign init_done = init_done_r;

    always @(posedge clk or negedge spi_rst_n) begin
        if (!spi_rst_n) begin
            init_state    <= I_IDLE;
            init_step     <= INIT_STEP_FLASH_RST_EN;
            init_done_r   <= 1'b0;
            init_spi_clk  <= 1'b0;
            init_flash_cs <= 1'b1;
            init_ram_cs   <= 1'b1;
            init_data_out <= 4'b0000;
            init_data_oe  <= 4'b0000;
            init_shift    <= 8'h00;
            init_bit_cnt  <= 3'd0;
            init_wait_cnt <= {INIT_WAIT_BITS{1'b0}};
            init_byte_idx <= 3'd0;
        end else begin
            case (init_state)
                I_IDLE: begin
                    init_done_r   <= 1'b0;
                    init_spi_clk  <= 1'b0;
                    init_flash_cs <= 1'b1;
                    init_ram_cs   <= 1'b1;
                    init_data_oe  <= 4'b0000;
                    init_wait_cnt <= INIT_POWER_WAIT_CYCLES;
                    init_state    <= I_WAIT_PWR;
                end

                I_WAIT_PWR: begin
                    if (init_wait_cnt != {INIT_WAIT_BITS{1'b0}})
                        init_wait_cnt <= init_wait_cnt - {{(INIT_WAIT_BITS-1){1'b0}}, 1'b1};
                    else
                        init_state <= I_LOAD;
                end

                I_LOAD: begin
                    if (init_step >= INIT_STEP_END) begin
                        init_state <= I_DONE;
                    end else begin
                        init_spi_clk  <= 1'b0;
                        init_flash_cs <= 1'b0;
                        init_ram_cs   <= 1'b1;
                        init_byte_idx <= 3'd0;
                        init_shift    <= init_byte(init_step, 3'd0);
                        init_bit_cnt  <= init_use_quad_w ? 3'd1 : 3'd7;
                        init_state    <= I_SHIFT_LOW;
                    end
                end

                I_SHIFT_LOW: begin
                    init_spi_clk <= 1'b0;
                    if (init_use_quad_w) begin
                        init_data_oe  <= 4'b1111;
                        init_data_out <= init_shift[7:4];
                    end else begin
                        // SPI command: IO0 = MOSI, IO1 = MISO released.
                        init_data_oe  <= 4'b0001;
                        init_data_out <= {3'b000, init_shift[7]};
                    end
                    init_state <= I_SHIFT_HIGH;
                end

                I_SHIFT_HIGH: begin
                    init_spi_clk <= 1'b1;
                    if (init_bit_cnt == 3'd0) begin
                        if (init_byte_idx + 3'd1 >= init_bytes_left_w) begin
                            init_state <= I_CS_HIGH;
                        end else begin
                            init_byte_idx <= init_byte_idx + 3'd1;
                            init_shift    <= init_byte(init_step, init_byte_idx + 3'd1);
                            init_bit_cnt  <= init_use_quad_w ? 3'd1 : 3'd7;
                            init_state    <= I_SHIFT_LOW;
                        end
                    end else begin
                        if (init_use_quad_w)
                            init_shift <= {init_shift[3:0], 4'h0};
                        else
                            init_shift <= {init_shift[6:0], 1'b0};
                        init_bit_cnt <= init_bit_cnt - 3'd1;
                        init_state   <= I_SHIFT_LOW;
                    end
                end

                I_CS_HIGH: begin
                    init_spi_clk <= 1'b0;
                    init_data_oe <= 4'b0000;

                    // Keep flash CS low between EBh command and the quad address/mode/dummy part.
                    if (init_step == INIT_STEP_FLASH_EB) begin
                        init_flash_cs <= 1'b0;
                        init_ram_cs   <= 1'b1;
                        init_step     <= INIT_STEP_FLASH_CONT;
                        init_state    <= I_LOAD;
                    end else begin
                        init_flash_cs <= 1'b1;
                        init_ram_cs   <= 1'b1;
                        init_wait_cnt <= init_gap_cycles(init_step);
                        init_state    <= I_GAP;
                    end
                end

                I_GAP: begin
                    if (init_wait_cnt != {INIT_WAIT_BITS{1'b0}})
                        init_wait_cnt <= init_wait_cnt - {{(INIT_WAIT_BITS-1){1'b0}}, 1'b1};
                    else begin
                        init_step  <= init_step + 4'd1;
                        init_state <= I_LOAD;
                    end
                end

                I_DONE: begin
                    init_done_r   <= 1'b1;
                    init_spi_clk  <= 1'b0;
                    init_flash_cs <= 1'b1;
                    init_ram_cs   <= 1'b1;
                    init_data_oe  <= 4'b0000;
                end
            endcase
        end
    end

// ============================================================
// 3) Runtime memory core
// ============================================================

    localparam C_IDLE        = 4'd0;
    localparam C_FLASH_ADDR  = 4'd1;
    localparam C_FLASH_MODE  = 4'd2;
    localparam C_FLASH_DUMMY = 4'd3;
    localparam C_FLASH_DATA  = 4'd4;
    localparam C_RAM_CMD     = 4'd5;
    localparam C_RAM_ADDR    = 4'd6;
    localparam C_RAM_DATA    = 4'd7;
    localparam C_FINISH      = 4'd8;

    reg [3:0]  core_state;
    reg        core_is_writing;
    reg [15:0] core_read_shift;
    reg [4:0]  core_count;
    reg [15:0] core_read_word_r;

    assign core_busy      = (core_state != C_IDLE);
    assign core_read_word = core_read_word_r;

    // Address mapping. CPU address is word address, external memory is byte address.
    wire [23:0] flash_byte_addr = {7'b0000000, core_addr_cpu, 1'b0};
    wire [23:0] ram_byte_addr   = {1'b0, 6'b000000, core_addr_cpu, 1'b0};

    wire ram_cmd_mosi = (core_count == 5'd1) ||
                        ((core_count == 5'd0) && !core_is_writing); // write=02h, read=03h

    always @(posedge clk or negedge spi_rst_n) begin
        if (!spi_rst_n) begin
            core_state       <= C_IDLE;
            core_spi_clk     <= 1'b0;
            core_flash_cs    <= 1'b1;
            core_ram_cs      <= 1'b1;
            core_data_oe     <= 4'b0000;
            core_is_writing  <= 1'b0;
            core_read_shift  <= 16'h0000;
            core_count       <= 5'd0;
            core_read_word_r <= 16'h0000;
        end else if (!init_done) begin
            core_state     <= C_IDLE;
            core_spi_clk   <= 1'b0;
            core_flash_cs  <= 1'b1;
            core_ram_cs    <= 1'b1;
            core_data_oe   <= 4'b0000;
        end else begin
            if (core_state == C_IDLE) begin
                core_spi_clk  <= 1'b0;
                core_data_oe  <= 4'b0000;
                core_flash_cs <= 1'b1;
                core_ram_cs   <= 1'b1;

                if (core_start_read || core_start_write) begin
                    core_is_writing <= core_start_write;
                    core_read_shift <= 16'h0000;

                    if (core_target_ram) begin
                        // RAM stays plain SPI.
                        core_flash_cs <= 1'b1;
                        core_ram_cs   <= 1'b0;
                        core_data_oe  <= 4'b0001; // IO0 MOSI only
                        core_count    <= 5'd7;    // 8 SPI command bits
                        core_state    <= C_RAM_CMD;
                    end else begin
                        // Flash is already in continuous QSPI read mode.
                        core_flash_cs <= 1'b0;
                        core_ram_cs   <= 1'b1;
                        core_data_oe  <= 4'b1111;
                        core_count    <= 5'd5; // 6 QSPI address nibbles
                        core_state    <= C_FLASH_ADDR;
                    end
                end
            end else if (core_state == C_FINISH) begin
                // Hold CS low for one extra system clock with SCK low, then release.
                core_spi_clk    <= 1'b0;
                core_data_oe    <= 4'b0000;
                core_flash_cs   <= 1'b1;
                core_ram_cs     <= 1'b1;
                core_is_writing <= 1'b0;
                core_state      <= C_IDLE;
            end else begin
                // Two system clocks per external SPI/QSPI clock.
                core_spi_clk <= !core_spi_clk;

                // Advance/sample on the high phase just before we drive SCK low.
                if (core_spi_clk) begin
                    case (core_state)
                        C_FLASH_ADDR: begin
                            if (core_count == 5'd0) begin
                                core_count <= 5'd1; // 2 QSPI mode nibbles: A,0
                                core_state <= C_FLASH_MODE;
                            end else begin
                                core_count <= core_count - 5'd1;
                            end
                        end

                        C_FLASH_MODE: begin
                            if (core_count == 5'd0) begin
                                core_data_oe <= 4'b0000;
                                core_count   <= 5'd3; // 4 QSPI dummy clocks
                                core_state   <= C_FLASH_DUMMY;
                            end else begin
                                core_count <= core_count - 5'd1;
                            end
                        end

                        C_FLASH_DUMMY: begin
                            if (core_count == 5'd0) begin
                                core_count <= 5'd3; // 4 QSPI data clocks = 16 bits
                                core_state <= C_FLASH_DATA;
                            end else begin
                                core_count <= core_count - 5'd1;
                            end
                        end

                        C_FLASH_DATA: begin
                            core_read_shift <= {core_read_shift[11:0], spi_data_in};
                            if (core_count == 5'd0) begin
                                core_read_word_r <= {core_read_shift[11:0], spi_data_in};
                                core_state       <= C_FINISH;
                            end else begin
                                core_count <= core_count - 5'd1;
                            end
                        end

                        C_RAM_CMD: begin
                            if (core_count == 5'd0) begin
                                core_count <= 5'd23; // 24 SPI address bits
                                core_state <= C_RAM_ADDR;
                            end else begin
                                core_count <= core_count - 5'd1;
                            end
                        end

                        C_RAM_ADDR: begin
                            if (core_count == 5'd0) begin
                                core_count <= 5'd15; // 16 data bits
                                core_state <= C_RAM_DATA;
                                if (core_is_writing)
                                    core_data_oe <= 4'b0001; // keep driving MOSI
                                else
                                    core_data_oe <= 4'b0000; // release bus, RAM drives IO1/MISO
                            end else begin
                                core_count <= core_count - 5'd1;
                            end
                        end

                        C_RAM_DATA: begin
                            if (core_is_writing) begin
                                if (core_count == 5'd0) begin
                                    core_state <= C_FINISH;
                                end else begin
                                    core_count <= core_count - 5'd1;
                                end
                            end else begin
                                core_read_shift <= {core_read_shift[14:0], spi_data_in[1]};
                                if (core_count == 5'd0) begin
                                    core_read_word_r <= {core_read_shift[14:0], spi_data_in[1]};
                                    core_state       <= C_FINISH;
                                end else begin
                                    core_count <= core_count - 5'd1;
                                end
                            end
                        end

                        default: begin
                            core_state <= C_FINISH;
                        end
                    endcase
                end
            end
        end
    end

    always @(*) begin
        core_data_out = 4'b1111;

        case (core_state)
            C_FLASH_ADDR: begin
                case (core_count)
                    5'd5: core_data_out = flash_byte_addr[23:20];
                    5'd4: core_data_out = flash_byte_addr[19:16];
                    5'd3: core_data_out = flash_byte_addr[15:12];
                    5'd2: core_data_out = flash_byte_addr[11:8];
                    5'd1: core_data_out = flash_byte_addr[7:4];
                    default: core_data_out = flash_byte_addr[3:0];
                endcase
            end

            C_FLASH_MODE: begin
                core_data_out = (core_count == 5'd1) ? 4'hA : 4'h0;
            end

            C_FLASH_DUMMY: begin
                core_data_out = 4'b1111;
            end

            C_FLASH_DATA: begin
                core_data_out = 4'b1111;
            end

            C_RAM_CMD: begin
                // RAM SPI MOSI on IO0. IO1/2/3 are released by OE.
                core_data_out = {3'b111, ram_cmd_mosi};
            end

            C_RAM_ADDR: begin
                core_data_out = {3'b111, ram_byte_addr[core_count]};
            end

            C_RAM_DATA: begin
                if (core_is_writing)
                    core_data_out = {3'b111, core_write_word[core_count]};
                else
                    core_data_out = 4'b1111;
            end

            default: begin
                core_data_out = 4'b1111;
            end
        endcase
    end

endmodule
