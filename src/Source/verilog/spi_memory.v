module spi_memory_interface (
    input  wire        clk,           // System clock
    input  wire        spi_rst_n,       // Reset
    input  wire        st,            // Store (write) signal
    input  wire        ld,            // Load (read) signal
    input  wire [15:0] addr,          // 16-bit memory address
    input  wire [15:0] data_in,       // 16-bit data input (for write)
    output reg  [15:0] data_out,      // 16-bit data output (for read)
    output reg         spi_cs,        // SPI Chip Select (Active Low)
    output reg         spi_clk,       // SPI Clock
    output reg         busy,          // Busy signal
    output reg         spi_mosi,      // SPI MOSI (Master Out Slave In)
    input  wire        spi_miso      // SPI MISO (Master In Slave Out)

  );

  // Define FSM states

  localparam  IDLE = 4'b0000;
  localparam  START = 4'b0001;
  localparam  SEND_CMD = 4'b0010;
  localparam  SEND_ADDR = 4'b0011;
  localparam  WRITE_DATA = 4'b0100;
  localparam  READ_DATA = 4'b0101;
  localparam  STOP = 4'b0110;
  localparam  TOGGLECLKON = 4'b0111;
  localparam  decideFate = 4'b1000;

  localparam  STcom = 1;
  localparam  LDcom = 0;


  reg[4:0] state;
  reg[4:0] last_state;
  reg command;

  reg [7:0] shift_reg; // Shift register for SPI data
  reg [5:0] bit_cnt;   // Bit counter
  reg [2:0] byte_cnt;  // Byte counter
  reg [15:0] recv_data;// Temporary storage for received data

  reg [0:0] prev_command;
  reg [15:0] prev_addr;
  wire [23:0] spi_addr;
  assign spi_addr = {7'b0000000, addr, 1'b0};

  always @(posedge clk , negedge spi_rst_n)
  begin

    if (!spi_rst_n)
    begin
      state   <= IDLE;
      spi_cs  <= 1'b1;
      spi_clk <= 1'b0;
      spi_mosi <= 1'b0;
      busy    <= 1'b0;
      bit_cnt <= 3'b000;
      byte_cnt <= 3'b000;
      command <= STcom;
      state <= IDLE;
      last_state <= IDLE;
    end
    else
    begin
      case (state)
        IDLE:
        begin
          busy <= 1'b0;
          if (st || ld)
          begin
            state <= START;
            busy <= 1'b1;

            prev_command <= command;
            prev_addr <= addr;

            if (st)
            begin
              shift_reg <= 8'h02; // Write command
              command <= STcom;
            end

            else if (ld)
            begin
              shift_reg <= 8'h03; // Read command
              command <= LDcom;
            end

          end
        end

        START:
        begin
          spi_cs <=1'b0;
          bit_cnt <= 3'b000;
          byte_cnt <= 3'b000;
          state <= SEND_CMD;
        end

        SEND_CMD:
        begin
          spi_clk <= 0;
          if (bit_cnt < 8)
          begin
            spi_mosi <= shift_reg[7];   // Send MSB first
            shift_reg <= shift_reg << 1;
            last_state <= state;
            state <= TOGGLECLKON;
            bit_cnt <= bit_cnt + 1;
          end
          else
          begin
            state <= SEND_ADDR;
            shift_reg <= spi_addr[23:16] ;         // top address byte for 24-bit SPI flash
            bit_cnt <= 0;
            byte_cnt <= 0;
          end
        end

        SEND_ADDR:
        begin
          spi_clk <= 0;

          if (bit_cnt < 8)
          begin
            spi_mosi <= shift_reg[7];
            shift_reg <= shift_reg << 1;
            last_state <= state;
            state <= TOGGLECLKON;
            bit_cnt <= bit_cnt + 1;
          end
          else if (byte_cnt == 0)
          begin
            shift_reg <= spi_addr[15:8];    // middle address byte
            byte_cnt <= 1;
            bit_cnt <= 0;
          end
          else if (byte_cnt == 1)
          begin
            shift_reg <= spi_addr[7:0];     // low address byte
            byte_cnt <= 2;
            bit_cnt <= 0;
          end
          else
          begin
            state <= command ? WRITE_DATA : READ_DATA;
            shift_reg <= command ? data_in[15:8] : 8'h00;
            recv_data <= 16'h0000;
            bit_cnt <= 0;
            byte_cnt <= 0;
            spi_mosi <= 1'b0;
          end
        end

        WRITE_DATA:
        begin

          spi_clk <= 0;
          if (bit_cnt < 8)
          begin
            spi_mosi <= shift_reg[7];
            shift_reg <= shift_reg << 1;

            last_state <= state;
            state <= TOGGLECLKON;
            bit_cnt <= bit_cnt + 1;
          end
          else if (byte_cnt == 0)
          begin
            shift_reg <= data_in[7:0]; // Load low byte
            byte_cnt <= 1;
            bit_cnt <= 0;
          end
          else
          begin
            state <= decideFate; // Decide next state based on command
          end
        end

        READ_DATA:
        begin

          spi_clk <= 0;
          if (bit_cnt < 17)
          begin
            last_state<=state;

            if (bit_cnt<16)
              state <= TOGGLECLKON;
            bit_cnt <= bit_cnt + 1;
            recv_data[15:0] <= {recv_data[14:0], spi_miso}; // Shift left


          end
          else
          begin
            recv_data[15:0] <= {recv_data[14:0], spi_miso};
            data_out <= recv_data;
            state <= decideFate; // Decide next state based on command
            bit_cnt <= 0;
          end
        end


        STOP:
        begin

          spi_clk <= 0;
          spi_cs <= 1'b1;
          busy <= 1'b0;
          state <= IDLE;
        end

        TOGGLECLKON:
        begin
          spi_clk <= 1;
          state <= last_state;
        end

        decideFate:
        begin
          if (command == prev_command &&
              addr == prev_addr + 1 )
          begin
            // Continue without releasing CS
            shift_reg <= command ? data_in[15:8] : 8'h00;
            bit_cnt <= 0;
            byte_cnt <= 0;
            recv_data <= 0;
            spi_mosi <= 0;
            state <= command ? WRITE_DATA : READ_DATA;

            // Update previous address
            prev_addr <= addr;
          end
          else
          begin
            // End transaction
            state <= STOP;
          end
        end
        default :
          state <= STOP;

      endcase
    end

  end

endmodule
