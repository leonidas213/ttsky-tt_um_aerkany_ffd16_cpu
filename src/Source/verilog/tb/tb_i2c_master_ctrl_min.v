`timescale 1ns/1ps

module tb_i2c_master_ctrl_min;

  reg clk;
  reg rst_n;

  reg        wr_en;
  reg [3:0]  reg_addr;
  reg [15:0] cpu_din;
  wire [15:0] cpu_dout;

  wire sda_in;
  wire sda_out;
  wire scl_out;
  wire scl_oe;
  wire sda_oe;
  wire interrupt;

  // Open-drain bus model with pull-ups.
  wire scl_bus;
  wire sda_bus;

  reg slave_enabled;
  reg slave_sda_drive_low;

  assign scl_bus = scl_oe ? scl_out : 1'b1;
  assign sda_bus = (sda_oe || slave_sda_drive_low) ? 1'b0 : 1'b1;
  assign sda_in  = sda_bus;

  // DUT
  i2c_master_ctrl dut (
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

  // 100 MHz test clock.
  initial clk = 1'b0;
  always #5 clk = ~clk;

  // ------------------------------------------------------------
  // Small I2C register-device slave model
  // ------------------------------------------------------------
  // It behaves like a very small EEPROM/register-mapped sensor:
  //   write: START, 0xA0, register, data..., STOP
  //   read : START, 0xA0, register, repeated START, 0xA1, READ..., STOP
  //
  // Slave address is 0x50, so address bytes are:
  //   write = 8'hA0
  //   read  = 8'hA1
  // ------------------------------------------------------------
  localparam [6:0] SLAVE_ADDR = 7'h50;

  reg [7:0] slave_mem [0:255];
  reg [7:0] slave_reg_ptr;
  reg [7:0] slave_rx_shift;
  reg [7:0] slave_tx_shift;
  reg [7:0] slave_next_byte;
  reg [7:0] slave_last_rx_byte;
  reg [7:0] slave_last_bytes [0:15];

  reg       slave_active;
  reg       slave_tx_mode;
  reg       slave_addr_ok;
  reg       slave_rw;
  reg       slave_ack_this_byte;
  reg       slave_pending_tx;
  reg       slave_ack_enable;
  reg [3:0] slave_bit_pos;
  integer   slave_byte_count;
  integer   i;

  task slave_reset_state;
    begin
      slave_sda_drive_low = 1'b0;
      slave_active        = 1'b0;
      slave_tx_mode       = 1'b0;
      slave_addr_ok       = 1'b0;
      slave_rw            = 1'b0;
      slave_ack_this_byte = 1'b0;
      slave_pending_tx    = 1'b0;
      slave_bit_pos       = 4'd0;
      slave_byte_count    = 0;
      slave_rx_shift      = 8'd0;
      slave_tx_shift      = 8'd0;
      slave_next_byte     = 8'd0;
      slave_last_rx_byte  = 8'd0;
    end
  endtask

  task slave_init_memory;
    begin
      for (i = 0; i < 256; i = i + 1)
        slave_mem[i] = 8'h00;
      for (i = 0; i < 16; i = i + 1)
        slave_last_bytes[i] = 8'h00;
      slave_reg_ptr = 8'h00;
    end
  endtask

  task slave_process_rx_byte;
    input [7:0] b;
    begin
      slave_last_rx_byte = b;

      if (slave_byte_count < 16)
        slave_last_bytes[slave_byte_count] = b;

      // First byte after START is the I2C address byte.
      if (slave_byte_count == 0) begin
        slave_addr_ok       = (b[7:1] == SLAVE_ADDR);
        slave_rw            = b[0];
        slave_ack_this_byte = slave_ack_enable && (b[7:1] == SLAVE_ADDR);
        slave_pending_tx    = slave_ack_enable && (b[7:1] == SLAVE_ADDR) && b[0];
      end

      // Remaining bytes in a write transaction are register pointer/data.
      else if (slave_addr_ok && !slave_rw) begin
        slave_ack_this_byte = slave_ack_enable;
        slave_pending_tx    = 1'b0;

        if (slave_byte_count == 1) begin
          // Register address byte.
          slave_reg_ptr = b;
        end else begin
          // Data byte. Auto-increment like many sensors/EEPROMs.
          slave_mem[slave_reg_ptr] = b;
          slave_reg_ptr = slave_reg_ptr + 8'd1;
        end
      end

      else begin
        slave_ack_this_byte = 1'b0;
        slave_pending_tx    = 1'b0;
      end

      slave_byte_count = slave_byte_count + 1;
    end
  endtask

  // START or repeated START: SDA falls while SCL is high.
  always @(negedge sda_bus or negedge rst_n) begin
    if (!rst_n) begin
      slave_reset_state();
    end else if (scl_bus && slave_enabled) begin
      slave_active        <= 1'b1;
      slave_tx_mode       <= 1'b0;
      slave_addr_ok       <= 1'b0;
      slave_rw            <= 1'b0;
      slave_ack_this_byte <= 1'b0;
      slave_pending_tx    <= 1'b0;
      slave_bit_pos       <= 4'd0;
      slave_byte_count    <= 0;
      slave_rx_shift      <= 8'd0;
      slave_sda_drive_low <= 1'b0;
    end
  end

  // STOP: SDA rises while SCL is high.
  always @(posedge sda_bus or negedge rst_n) begin
    if (!rst_n) begin
      slave_active        <= 1'b0;
      slave_tx_mode       <= 1'b0;
      slave_sda_drive_low <= 1'b0;
    end else if (scl_bus) begin
      slave_active        <= 1'b0;
      slave_tx_mode       <= 1'b0;
      slave_sda_drive_low <= 1'b0;
      slave_bit_pos       <= 4'd0;
    end
  end

  // Sample receive bits, or observe master's ACK/NACK during slave transmit.
  always @(posedge scl_bus or negedge rst_n) begin
    if (!rst_n) begin
      slave_reset_state();
    end else if (slave_active && slave_enabled) begin
      if (!slave_tx_mode) begin
        if (slave_bit_pos < 4'd8) begin
          slave_next_byte = {slave_rx_shift[6:0], sda_bus};
          slave_rx_shift <= slave_next_byte;

          if (slave_bit_pos == 4'd7)
            slave_process_rx_byte(slave_next_byte);

          slave_bit_pos <= slave_bit_pos + 4'd1;
        end else begin
          // ACK clock is complete. Do NOT release SDA while SCL is high,
          // otherwise the monitor sees a false STOP. Release/advance on
          // the following SCL falling edge.
          slave_bit_pos       <= 4'd0;

          if (slave_pending_tx) begin
            slave_tx_mode    <= 1'b1;
            slave_tx_shift   <= slave_mem[slave_reg_ptr];
            slave_pending_tx <= 1'b0;
          end
        end
      end else begin
        if (slave_bit_pos < 4'd8) begin
          slave_bit_pos <= slave_bit_pos + 4'd1;
        end else begin
          // 9th clock after TX byte: master ACKs with 0, NACKs with 1.
          slave_sda_drive_low <= 1'b0;
          slave_bit_pos       <= 4'd0;

          if (sda_bus) begin
            // Master NACK: stop transmitting until next START.
            slave_tx_mode <= 1'b0;
          end else begin
            // Master ACK: prepare next byte.
            slave_reg_ptr  <= slave_reg_ptr + 8'd1;
            slave_tx_shift <= slave_mem[slave_reg_ptr + 8'd1];
          end
        end
      end
    end
  end

  // Drive ACK during receive, or data bits during transmit.
  always @(negedge scl_bus or negedge rst_n) begin
    if (!rst_n) begin
      slave_sda_drive_low <= 1'b0;
    end else if (slave_active && slave_enabled) begin
      if (!slave_tx_mode) begin
        if (slave_bit_pos == 4'd8)
          slave_sda_drive_low <= slave_ack_this_byte;
        else
          slave_sda_drive_low <= 1'b0;
      end else begin
        if (slave_bit_pos < 4'd8)
          slave_sda_drive_low <= ~slave_tx_shift[7 - slave_bit_pos];
        else
          slave_sda_drive_low <= 1'b0; // release for master's ACK/NACK
      end
    end else begin
      slave_sda_drive_low <= 1'b0;
    end
  end

  // ------------------------------------------------------------
  // CPU bus helper tasks
  // ------------------------------------------------------------
  task cpu_write;
    input [3:0]  addr;
    input [15:0] data;
    begin
      @(negedge clk);
      reg_addr = addr;
      cpu_din  = data;
      wr_en    = 1'b1;
      @(negedge clk);
      wr_en    = 1'b0;
      cpu_din  = 16'd0;
    end
  endtask

  task cpu_read;
    input  [3:0]  addr;
    output [15:0] data;
    begin
      @(negedge clk);
      reg_addr = addr;
      #1;
      data = cpu_dout;
    end
  endtask

  task wait_done;
    integer timeout;
    reg [15:0] st;
    begin
      timeout = 0;
      cpu_read(4'h1, st);
      while ((st[2] !== 1'b1) && (timeout < 30000)) begin
        @(posedge clk);
        timeout = timeout + 1;
        reg_addr = 4'h1;
        #1;
        st = cpu_dout;
      end

      if (timeout >= 30000) begin
        $display("FAIL: timeout waiting for DONE at time %0t", $time);
        $finish;
      end
    end
  endtask

  task clear_status;
    begin
      // Clear DONE, ACK_ERROR, RX_VALID sticky bits.
      cpu_write(4'h1, 16'h001C);
    end
  endtask

  task i2c_write_byte;
    input [7:0] data;
    input       send_start;
    input       send_stop;
    output [15:0] status_out;
    reg [15:0] cmd;
    begin
      clear_status();
      cpu_write(4'h3, {8'h00, data});

      cmd = 16'h0004; // WRITE
      if (send_start) cmd = cmd | 16'h0001;
      if (send_stop)  cmd = cmd | 16'h0002;

      cpu_write(4'h4, cmd);
      wait_done();
      cpu_read(4'h1, status_out);
    end
  endtask

  task i2c_read_byte;
    input       send_start;
    input       send_stop;
    input       send_nack;
    output [7:0] data_out;
    output [15:0] status_out;
    reg [15:0] cmd;
    reg [15:0] data_reg;
    begin
      clear_status();

      cmd = 16'h0008; // READ
      if (send_start) cmd = cmd | 16'h0001;
      if (send_stop)  cmd = cmd | 16'h0002;
      if (send_nack)  cmd = cmd | 16'h0010;

      cpu_write(4'h4, cmd);
      wait_done();
      cpu_read(4'h1, status_out);
      cpu_read(4'h3, data_reg);
      data_out = data_reg[7:0];
    end
  endtask

  task check_no_ack_error;
    input [15:0] st;
    begin
      if (st[3] !== 1'b0) begin
        $display("FAIL: unexpected ACK_ERROR. status=0x%04h", st);
        $finish;
      end
    end
  endtask

  // ------------------------------------------------------------
  // Test sequence
  // Register map used by i2c_master_ctrl_min:
  //   0x0 control: bit0 enable, bit1 irq_enable
  //   0x1 status : bit0 busy, bit1 bus_active, bit2 done,
  //                bit3 ack_error, bit4 rx_valid, bit5 interrupt-pending mirror
  //   0x2 divider: fixed divider readback
  //   0x3 data   : write TX byte / read RX byte
  //   0x4 command: bit0 start, bit1 stop, bit2 write, bit3 read, bit4 nack
  // ------------------------------------------------------------
  reg [15:0] status;
  reg [15:0] data_reg;
  reg [7:0]  read_data;

  initial begin
    $dumpfile("tb_i2c_master_ctrl_min_reg_rw.vcd");
    $dumpvars(0, tb_i2c_master_ctrl_min);

    rst_n            = 1'b0;
    wr_en            = 1'b0;
    reg_addr         = 4'd0;
    cpu_din          = 16'd0;
    slave_enabled    = 1'b1;
    slave_ack_enable = 1'b1;
    slave_reset_state();
    slave_init_memory();

    repeat (8) @(posedge clk);
    rst_n = 1'b1;
    repeat (4) @(posedge clk);

    // ----------------------------------------------------------
    // TEST 1: CPU-visible register read/write sanity
    // ----------------------------------------------------------
    $display("TEST 1: CPU register read/write sanity");

    cpu_read(4'h0, data_reg);
    if (data_reg[1:0] !== 2'b00) begin
      $display("FAIL: control reset value wrong: 0x%04h", data_reg);
      $finish;
    end

    cpu_write(4'h0, 16'h0003); // enable=1, irq_enable=1
    cpu_read(4'h0, data_reg);
    if (data_reg[1:0] !== 2'b11) begin
      $display("FAIL: control readback wrong: 0x%04h", data_reg);
      $finish;
    end

    cpu_read(4'h2, data_reg);
    if (data_reg[7:0] !== 8'd20) begin
      $display("FAIL: fixed divider readback wrong: 0x%04h", data_reg);
      $finish;
    end

    $display("PASS: CPU register read/write sanity");

    // ----------------------------------------------------------
    // TEST 2: I2C address write ACK
    // ----------------------------------------------------------
    $display("TEST 2: START + WRITE slave address 0xA0 + STOP, expect ACK");
    slave_ack_enable = 1'b1;
    i2c_write_byte(8'hA0, 1'b1, 1'b1, status);
    check_no_ack_error(status);

    if (slave_last_rx_byte !== 8'hA0) begin
      $display("FAIL: slave received 0x%02h, expected address 0xA0", slave_last_rx_byte);
      $finish;
    end

    $display("PASS: address write ACK test, status=0x%04h", status);

    // ----------------------------------------------------------
    // TEST 3: Wrong I2C address should NACK
    // ----------------------------------------------------------
    $display("TEST 3: START + WRITE wrong address 0xA2 + STOP, expect ACK_ERROR");
    i2c_write_byte(8'hA2, 1'b1, 1'b1, status);

    if (status[3] !== 1'b1) begin
      $display("FAIL: ACK_ERROR not set for wrong address. status=0x%04h", status);
      $finish;
    end

    $display("PASS: wrong-address NACK test, status=0x%04h", status);

    // ----------------------------------------------------------
    // TEST 4: I2C slave register write
    // Sequence: START 0xA0, register 0x10, data 0xC3, STOP
    // ----------------------------------------------------------
    $display("TEST 4: I2C register write: dev=0x50 reg=0x10 data=0xC3");
    slave_ack_enable = 1'b1;

    i2c_write_byte(8'hA0, 1'b1, 1'b0, status); // address + write, keep bus active
    check_no_ack_error(status);

    i2c_write_byte(8'h10, 1'b0, 1'b0, status); // register pointer
    check_no_ack_error(status);

    i2c_write_byte(8'hC3, 1'b0, 1'b1, status); // data + STOP
    check_no_ack_error(status);

    if (slave_mem[8'h10] !== 8'hC3) begin
      $display("FAIL: slave_mem[0x10]=0x%02h, expected 0xC3", slave_mem[8'h10]);
      $finish;
    end

    $display("PASS: I2C register write");

    // ----------------------------------------------------------
    // TEST 5: I2C slave register read-back
    // Sequence: START 0xA0, register 0x10,
    //           repeated START 0xA1, READ byte + NACK + STOP
    // ----------------------------------------------------------
    $display("TEST 5: I2C register read: dev=0x50 reg=0x10, expect 0xC3");

    i2c_write_byte(8'hA0, 1'b1, 1'b0, status); // address + write
    check_no_ack_error(status);

    i2c_write_byte(8'h10, 1'b0, 1'b0, status); // register pointer
    check_no_ack_error(status);

    i2c_write_byte(8'hA1, 1'b1, 1'b0, status); // repeated START + address + read
    check_no_ack_error(status);

    i2c_read_byte(1'b0, 1'b1, 1'b1, read_data, status); // read + NACK + STOP

    if (status[4] !== 1'b1) begin
      $display("FAIL: RX_VALID not set after register read. status=0x%04h", status);
      $finish;
    end

    if (read_data !== 8'hC3) begin
      $display("FAIL: register read returned 0x%02h, expected 0xC3", read_data);
      $finish;
    end

    $display("PASS: I2C register read-back, data=0x%02h", read_data);

    $display("ALL TESTS PASSED");
    repeat (20) @(posedge clk);
    $finish;
  end

endmodule
