module i2c_master_ctrl (
    input              clk,
    input              rst_n,

    input              wr_en,
    input      [3:0]   reg_addr,
    input      [15:0]  cpu_din,
    output reg [15:0]  cpu_dout,

    input              sda_in,
    output             sda_out,
    output reg         scl_out,
    output             scl_oe,
    output reg         sda_oe,

    output             interrupt
  );

  // Minimal fixed-speed I2C master.
  // I2C SCL is roughly: clk / (3 * (I2C_DIV + 1))
  // Example: 25 MHz clock, I2C_DIV=20 gives about 397 kHz.
  localparam [7:0] I2C_DIV = 8'd20;

  assign sda_out   = 1'b0;          // open-drain style: only drive low
  assign scl_oe    = enable | busy | bus_active;
  assign interrupt = irq_enable & done;

  localparam ST_IDLE  = 3'd0;
  localparam ST_START = 3'd1;
  localparam ST_BIT   = 3'd2;
  localparam ST_ACK   = 3'd3;
  localparam ST_STOP  = 3'd4;

  reg        enable;
  reg        irq_enable;

  reg        busy;
  reg        bus_active;
  reg        done;
  reg        ack_error;
  reg        rx_valid;

  reg [7:0]  divcnt;
  reg [7:0]  tx_data;
  reg [7:0]  rx_data;
  reg [7:0]  shift;
  reg [2:0]  bit_count;

  reg        do_read;
  reg        do_byte;
  reg        do_stop;
  reg        do_nack;

  reg [2:0]  state;
  reg [1:0]  phase;

  wire tick = (divcnt == 8'd0);

  wire cmd_hit   = wr_en && (reg_addr == 4'h4) && enable && !busy;
  wire cmd_any   = cpu_din[0] | cpu_din[1] | cpu_din[2] | cpu_din[3];
  wire cmd_start = cpu_din[0];
  wire cmd_stop  = cpu_din[1];
  wire cmd_write = cpu_din[2];
  wire cmd_read  = cpu_din[3];

  always @(posedge clk or negedge rst_n)
  begin
    if (!rst_n)
    begin
      enable     <= 1'b0;
      irq_enable <= 1'b0;
      busy       <= 1'b0;
      bus_active <= 1'b0;
      done       <= 1'b0;
      ack_error  <= 1'b0;
      rx_valid   <= 1'b0;
      divcnt     <= 8'd0;
      tx_data    <= 8'd0;
      rx_data    <= 8'd0;
      shift      <= 8'd0;
      bit_count  <= 3'd0;
      do_read    <= 1'b0;
      do_byte    <= 1'b0;
      do_stop    <= 1'b0;
      do_nack    <= 1'b0;
      state      <= ST_IDLE;
      phase      <= 2'd0;
      scl_out    <= 1'b1;
      sda_oe     <= 1'b0;
    end
    else
    begin
      if (busy)
      begin
        if (tick)
          divcnt <= I2C_DIV;
        else
          divcnt <= divcnt - 8'd1;
      end
      else
      begin
        divcnt <= 8'd0;
      end

      if (wr_en)
      begin
        case (reg_addr)
          4'h0:
          begin
            enable     <= cpu_din[0];
            irq_enable <= cpu_din[1];
          end

          // Write 1 to clear sticky status bits.
          4'h1:
          begin
            if (cpu_din[2]) done      <= 1'b0;
            if (cpu_din[3]) ack_error <= 1'b0;
            if (cpu_din[4]) rx_valid  <= 1'b0;
          end

          4'h3:
          begin
            tx_data <= cpu_din[7:0];
          end
        endcase
      end

      if (cmd_hit && cmd_any)
      begin
        busy       <= 1'b1;
        done       <= 1'b0;
        ack_error  <= 1'b0;
        rx_valid   <= 1'b0;
        divcnt     <= 8'd0;
        phase      <= 2'd0;
        bit_count  <= 3'd7;
        do_read    <= cmd_read;
        do_byte    <= cmd_write | cmd_read;
        do_stop    <= cmd_stop;
        do_nack    <= cpu_din[4];
        shift      <= cmd_read ? 8'd0 : tx_data;

        if (cmd_start)
        begin
          state   <= ST_START;
          scl_out <= 1'b1;
          sda_oe  <= 1'b0;
        end
        else if (cmd_write || cmd_read)
        begin
          state   <= ST_BIT;
          scl_out <= 1'b0;
          sda_oe  <= cmd_read ? 1'b0 : ~tx_data[7];
        end
        else
        begin
          state   <= ST_STOP;
          scl_out <= 1'b0;
          sda_oe  <= 1'b1;
        end
      end
      else if (busy && tick)
      begin
        case (state)
          ST_START:
          begin
            case (phase)
              2'd0:
              begin
                scl_out <= 1'b1;
                sda_oe  <= 1'b0;
                phase   <= 2'd1;
              end

              2'd1:
              begin
                scl_out <= 1'b1;
                sda_oe  <= 1'b1;      // SDA falling while SCL high
                phase   <= 2'd2;
              end

              default:
              begin
                scl_out    <= 1'b0;
                bus_active <= 1'b1;
                phase      <= 2'd0;

                if (do_byte)
                begin
                  state  <= ST_BIT;
                  sda_oe <= do_read ? 1'b0 : ~tx_data[7];
                end
                else if (do_stop)
                begin
                  state  <= ST_STOP;
                  sda_oe <= 1'b1;
                end
                else
                begin
                  busy  <= 1'b0;
                  done  <= 1'b1;
                  state <= ST_IDLE;
                end
              end
            endcase
          end

          ST_BIT:
          begin
            case (phase)
              2'd0:
              begin
                scl_out <= 1'b0;
                sda_oe  <= do_read ? 1'b0 : ~shift[bit_count];
                phase   <= 2'd1;
              end

              2'd1:
              begin
                scl_out <= 1'b1;
                phase   <= 2'd2;
              end

              default:
              begin
                scl_out <= 1'b0;

                if (do_read)
                  shift[bit_count] <= sda_in;

                if (bit_count != 3'd0)
                begin
                  bit_count <= bit_count - 3'd1;
                  phase     <= 2'd0;
                end
                else
                begin
                  phase <= 2'd0;
                  state <= ST_ACK;
                end
              end
            endcase
          end

          ST_ACK:
          begin
            case (phase)
              2'd0:
              begin
                scl_out <= 1'b0;
                sda_oe  <= do_read ? ~do_nack : 1'b0; // read: ACK low unless NACK
                phase   <= 2'd1;
              end

              2'd1:
              begin
                scl_out <= 1'b1;
                if (!do_read && sda_in)
                  ack_error <= 1'b1;
                phase <= 2'd2;
              end

              default:
              begin
                scl_out <= 1'b0;
                sda_oe  <= 1'b0;
                phase   <= 2'd0;

                if (do_read)
                begin
                  rx_data  <= shift;
                  rx_valid <= 1'b1;
                end

                if (do_stop)
                begin
                  state  <= ST_STOP;
                  sda_oe <= 1'b1;
                end
                else
                begin
                  busy  <= 1'b0;
                  done  <= 1'b1;
                  state <= ST_IDLE;
                end
              end
            endcase
          end

          ST_STOP:
          begin
            case (phase)
              2'd0:
              begin
                scl_out <= 1'b0;
                sda_oe  <= 1'b1;
                phase   <= 2'd1;
              end

              2'd1:
              begin
                scl_out <= 1'b1;
                sda_oe  <= 1'b1;
                phase   <= 2'd2;
              end

              default:
              begin
                scl_out    <= 1'b1;
                sda_oe     <= 1'b0;   // SDA rising while SCL high
                bus_active <= 1'b0;
                busy       <= 1'b0;
                done       <= 1'b1;
                state      <= ST_IDLE;
                phase      <= 2'd0;
              end
            endcase
          end

          default:
          begin
            busy       <= 1'b0;
            bus_active <= 1'b0;
            state      <= ST_IDLE;
            scl_out    <= 1'b1;
            sda_oe     <= 1'b0;
            done       <= 1'b1;
            ack_error  <= 1'b1;
          end
        endcase
      end
    end
  end

  always @(*)
  begin
    cpu_dout = 16'd0;

    case (reg_addr)
      4'h0:
      begin
        cpu_dout[0] = enable;
        cpu_dout[1] = irq_enable;
      end

      4'h1:
      begin
        cpu_dout[0] = busy;
        cpu_dout[1] = bus_active;
        cpu_dout[2] = done;
        cpu_dout[3] = ack_error;
        cpu_dout[4] = rx_valid;
        cpu_dout[5] = done;       // minimal replacement for old irq_pending
      end

      4'h2:
      begin
        cpu_dout[7:0] = I2C_DIV;
      end

      4'h3:
      begin
        cpu_dout[7:0] = rx_data;
      end
    endcase
  end

endmodule
