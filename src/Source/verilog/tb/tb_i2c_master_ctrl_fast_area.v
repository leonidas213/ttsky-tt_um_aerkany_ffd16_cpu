`timescale 1ns/1ps
`default_nettype none

// Testbench for i2c_master_ctrl_fast_area.v
//
// Compile:
//   iverilog -g2005 -o i2c_tb.vvp i2c_master_ctrl_fast_area.v tb_i2c_master_ctrl_fast_area.v
//   vvp i2c_tb.vvp
//   gtkwave i2c_master_ctrl_fast_area_tb.vcd
//
// The DUT is instantiated with FAST_DIV=2 to make simulation short.
// In synthesis you can keep FAST_DIV=41 for ~400 kHz at 50 MHz.

module tb_i2c_master_ctrl_fast_area;

  reg clk;
  reg rst_n;

  reg         wr_en;
  reg  [3:0]  reg_addr;
  reg  [15:0] cpu_din;
  wire [15:0] cpu_dout;

  wire sda_in;
  wire sda_out;
  wire scl_out;
  wire scl_oe;
  wire sda_oe;
  wire interrupt;

  wire scl_bus;
  wire sda_bus;
  wire slave_sda_drive_low;

  // Fast simulation clock: 100 MHz
  initial clk = 1'b0;
  always #5 clk = ~clk;

  // Master SCL is output-value + output-enable.
  // Pull high when released.
  assign scl_bus = scl_oe ? scl_out : 1'b1;

  // SDA is open-drain: master or slave can pull low, otherwise pull high.
  assign sda_bus = (sda_oe || slave_sda_drive_low) ? 1'b0 : 1'b1;
  assign sda_in  = sda_bus;

  i2c_master_ctrl #(
    .FAST_DIV(6'd2)
  ) dut (
    .clk(clk),
    .rst_n(rst_n),

    .wr_en(wr_en),
    .reg_addr(reg_addr),
    .cpu_din(cpu_din),
    .cpu_dout(cpu_dout),

    .sda_in(sda_in),
    .sda_out(sda_out),
    .scl_out(scl_out),
    .scl_oe(scl_oe),
    .sda_oe(sda_oe),

    .interrupt(interrupt)
  );

  i2c_simple_slave_model #(
    .SLAVE_ADDR(7'h50),
    .READ_BYTE(8'h5A)
  ) slave (
    .scl(scl_bus),
    .sda(sda_bus),
    .sda_drive_low(slave_sda_drive_low)
  );

  localparam [15:0] CMD_START     = 16'h0001;
  localparam [15:0] CMD_STOP      = 16'h0002;
  localparam [15:0] CMD_WRITE     = 16'h0004;
  localparam [15:0] CMD_READ      = 16'h0008;
  localparam [15:0] CMD_READ_NACK = 16'h0010;

  integer errors;

  task cpu_write;
    input [3:0]  a;
    input [15:0] d;
    begin
      @(posedge clk);
      reg_addr <= a;
      cpu_din  <= d;
      wr_en    <= 1'b1;
      @(posedge clk);
      wr_en    <= 1'b0;
      cpu_din  <= 16'h0000;
    end
  endtask

  task clear_status;
    begin
      // clear done, ack_error, rx_valid, irq_pending
      cpu_write(4'h1, 16'h003C);
    end
  endtask

  task wait_done;
    input check_ack;
    integer timeout;
    begin
      timeout = 0;
      reg_addr = 4'h1;
      #1;
      while (cpu_dout[2] !== 1'b1 && timeout < 20000) begin
        @(posedge clk);
        reg_addr = 4'h1;
        #1;
        timeout = timeout + 1;
      end

      if (timeout >= 20000) begin
        $display("ERROR: timeout waiting for I2C done at time %0t", $time);
        errors = errors + 1;
      end else begin
        $display("I2C done: status=%04h time=%0t", cpu_dout, $time);
      end

      if (check_ack && cpu_dout[3]) begin
        $display("ERROR: ACK error at time %0t status=%04h", $time, cpu_dout);
        errors = errors + 1;
      end

      clear_status();
    end
  endtask

  task set_tx;
    input [7:0] b;
    begin
      cpu_write(4'h3, {8'h00, b});
    end
  endtask

  task command;
    input [15:0] cmd;
    input        check_ack;
    begin
      cpu_write(4'h4, cmd);
      wait_done(check_ack);
    end
  endtask

  task i2c_write_byte;
    input [7:0] b;
    input       with_start;
    input       with_stop;
    reg [15:0] cmd;
    begin
      set_tx(b);
      cmd = CMD_WRITE;
      if (with_start) cmd = cmd | CMD_START;
      if (with_stop)  cmd = cmd | CMD_STOP;
      $display("MASTER WRITE byte=%02h start=%0d stop=%0d", b, with_start, with_stop);
      command(cmd, 1'b1);
    end
  endtask

  task i2c_read_byte_nack_stop;
    output [7:0] b;
    begin
      $display("MASTER READ byte with NACK+STOP");
      command(CMD_READ | CMD_READ_NACK | CMD_STOP, 1'b0);
      reg_addr = 4'h3;
      #1;
      b = cpu_dout[7:0];
      $display("MASTER READ got %02h", b);
    end
  endtask

  reg [7:0] rb;

  initial begin
    $dumpfile("i2c_master_ctrl_fast_area_tb.vcd");
    $dumpvars(0, tb_i2c_master_ctrl_fast_area);

    errors   = 0;
    rst_n    = 1'b0;
    wr_en    = 1'b0;
    reg_addr = 4'h0;
    cpu_din  = 16'h0000;

    repeat (10) @(posedge clk);
    rst_n = 1'b1;
    repeat (5) @(posedge clk);

    // Enable I2C master. IRQ disabled.
    cpu_write(4'h0, 16'h0001);

    // ------------------------------------------------------------
    // Test 1: simple write transaction
    // START + address write, data byte, data byte + STOP
    // Expected slave bytes: A0, 10, 33
    // ------------------------------------------------------------
    $display("\n--- TEST 1: WRITE 0x33 to slave reg 0x10 ---");
    i2c_write_byte(8'hA0, 1'b1, 1'b0); // 7'h50 + W
    i2c_write_byte(8'h10, 1'b0, 1'b0); // register index
    i2c_write_byte(8'h33, 1'b0, 1'b1); // data + stop

    repeat (20) @(posedge clk);

    if (slave.captured[0] !== 8'hA0) begin
      $display("ERROR: slave captured[0]=%02h expected A0", slave.captured[0]);
      errors = errors + 1;
    end
    if (slave.captured[1] !== 8'h10) begin
      $display("ERROR: slave captured[1]=%02h expected 10", slave.captured[1]);
      errors = errors + 1;
    end
    if (slave.captured[2] !== 8'h33) begin
      $display("ERROR: slave captured[2]=%02h expected 33", slave.captured[2]);
      errors = errors + 1;
    end

    // ------------------------------------------------------------
    // Test 2: register-style read transaction
    // START A0, register 10, REPEATED START A1, READ NACK STOP
    // Slave returns 0x5A.
    // ------------------------------------------------------------
    $display("\n--- TEST 2: READ 0x5A from slave ---");
    i2c_write_byte(8'hA0, 1'b1, 1'b0); // address + W
    i2c_write_byte(8'h10, 1'b0, 1'b0); // register index
    i2c_write_byte(8'hA1, 1'b1, 1'b0); // repeated-start + address + R
    i2c_read_byte_nack_stop(rb);

    if (rb !== 8'h5A) begin
      $display("ERROR: read byte=%02h expected 5A", rb);
      errors = errors + 1;
    end

    repeat (40) @(posedge clk);

    if (errors == 0) begin
      $display("\nPASS: I2C fast-area master test passed.");
    end else begin
      $display("\nFAIL: I2C fast-area master test had %0d error(s).", errors);
    end

    $finish;
  end

endmodule


// Very small behavioral I2C slave model for simulation only.
// - Always ACKs bytes.
// - Captures received bytes into captured[0..7].
// - If it sees address {SLAVE_ADDR, 1'b1}, it returns READ_BYTE.
module i2c_simple_slave_model #(
  parameter [6:0] SLAVE_ADDR = 7'h50,
  parameter [7:0] READ_BYTE  = 8'h5A
)(
  input  wire scl,
  input  wire sda,
  output reg  sda_drive_low
);

  localparam SL_IDLE = 2'd0;
  localparam SL_RX   = 2'd1;
  localparam SL_ACK  = 2'd2;
  localparam SL_TX   = 2'd3;

  reg [1:0] state;
  reg [2:0] bit_idx;
  reg [7:0] shift;
  reg [3:0] byte_count;
  reg       active;
  reg       last_rw;
  reg       addr_match;
  reg [7:0] captured [0:7];

  integer i;

  initial begin
    state         = SL_IDLE;
    bit_idx       = 3'd0;
    shift         = 8'h00;
    byte_count    = 4'd0;
    active        = 1'b0;
    last_rw       = 1'b0;
    addr_match    = 1'b0;
    sda_drive_low = 1'b0;
    for (i = 0; i < 8; i = i + 1)
      captured[i] = 8'h00;
  end

  // START or repeated START: SDA falling while SCL high.
  always @(negedge sda) begin
    if (scl === 1'b1) begin
      active        <= 1'b1;
      state         <= SL_RX;
      bit_idx       <= 3'd0;
      shift         <= 8'h00;
      byte_count    <= 4'd0;
      sda_drive_low <= 1'b0;
      $display("SLAVE: START at %0t", $time);
    end
  end

  // STOP: SDA rising while SCL high.
  always @(posedge sda) begin
    if (scl === 1'b1 && active) begin
      active        <= 1'b0;
      state         <= SL_IDLE;
      sda_drive_low <= 1'b0;
      $display("SLAVE: STOP at %0t", $time);
    end
  end

  // Sample data on SCL rising edge.
  always @(posedge scl) begin
    if (active) begin
      case (state)
        SL_RX: begin
          shift <= {shift[6:0], sda};

          if (bit_idx == 3'd7) begin
            captured[byte_count[2:0]] <= {shift[6:0], sda};
            $display("SLAVE: RX byte[%0d] = %02h at %0t",
                     byte_count, {shift[6:0], sda}, $time);

            if (byte_count == 4'd0) begin
              last_rw    <= sda;
              addr_match <= (shift[6:0] == SLAVE_ADDR);
            end

            byte_count <= byte_count + 4'd1;
            bit_idx    <= 3'd0;
            state      <= SL_ACK;
          end else begin
            bit_idx <= bit_idx + 3'd1;
          end
        end

        SL_ACK: begin
          // Master samples ACK on this rising edge.
          // After ACK, either receive more bytes or transmit read data.
          if (byte_count == 4'd1 && last_rw && addr_match) begin
            state   <= SL_TX;
            bit_idx <= 3'd0;
          end else begin
            state   <= SL_RX;
            bit_idx <= 3'd0;
          end
        end

        SL_TX: begin
          if (bit_idx == 3'd7) begin
            bit_idx <= 3'd0;
            state   <= SL_IDLE; // one-byte read model
          end else begin
            bit_idx <= bit_idx + 3'd1;
          end
        end

        default: begin
          state <= SL_IDLE;
        end
      endcase
    end
  end

  // Change driven SDA only while SCL is low.
  always @(negedge scl) begin
    if (!active) begin
      sda_drive_low <= 1'b0;
    end else begin
      case (state)
        SL_ACK: begin
          // Always ACK by pulling SDA low.
          sda_drive_low <= 1'b1;
        end

        SL_TX: begin
          // Drive READ_BYTE MSB first. Pull low for 0, release for 1.
          sda_drive_low <= ~READ_BYTE[3'd7 - bit_idx];
        end

        default: begin
          sda_drive_low <= 1'b0;
        end
      endcase
    end
  end

endmodule

`default_nettype wire
