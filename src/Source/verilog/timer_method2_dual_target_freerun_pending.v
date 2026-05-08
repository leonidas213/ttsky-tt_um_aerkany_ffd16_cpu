// Method 2: recommended smaller/cleaner dual-target timer.
// Same module name + same ports as timer_small.v.
// One free-running counter, two compare targets, pending flags.
// timerTargetAddr     = target0
// timerSyncStartAddr  = target1 write/read, except dOut=0/1 keeps old sync-start behavior
// timerResetAddr write bits:
//   dOut[0] = reset counter + prescaler + clear both pending flags
//   dOut[1] = clear irq0 pending
//   dOut[2] = clear irq1 pending
// timerConfigAddr read returns {7'b0, irq1_pending, irq0_pending, conf[6:0]}

module timer (
    input  [15:0] dOut,
    input  [4:0] Addr,
    input         ioW,
    input         C,
    input         InterLock,
    input  [4:0] timerConfigAddr,
    input  [4:0] timerTargetAddr,
    input  [4:0] timerResetAddr,
    input  [4:0] timerReadAddr,
    input  [4:0] timerSyncStartAddr,
    input         rst_n,
    output [15:0] TimerOut,
    output        timer_interrupt
  );

  reg [15:0] target0;
  reg [15:0] target1;
  reg [15:0] count;
  reg [10:0] prescale_cnt;
  reg [6:0]  conf;
  reg        irq0_pending;
  reg        irq1_pending;

  wire wr_conf   = ioW && (Addr == timerConfigAddr);
  wire wr_target0 = ioW && (Addr == timerTargetAddr);
  wire wr_reset  = ioW && (Addr == timerResetAddr);
  wire wr_sync_or_target1 = ioW && (Addr == timerSyncStartAddr);

  wire rd_count  = (Addr == timerReadAddr);
  wire rd_target0 = (Addr == timerTargetAddr);
  wire rd_target1 = (Addr == timerSyncStartAddr);
  wire rd_conf   = (Addr == timerConfigAddr);

  wire       timer_en     = conf[0];
  wire [3:0] prescaler    = conf[4:1];
  wire       irq_en       = conf[6];

  wire       target0_valid = (target0 != 16'h0000);
  wire       target1_valid = (target1 != 16'h0000);
  wire       match0        = target0_valid && (count == target0);
  wire       match1        = target1_valid && (count == target1);

  reg tick;
  always @(*) begin
    case (prescaler)
      4'd0:  tick = 1'b1;
      4'd1:  tick = prescale_cnt[0];
      4'd2:  tick = &prescale_cnt[1:0];
      4'd3:  tick = &prescale_cnt[2:0];
      4'd4:  tick = &prescale_cnt[3:0];
      4'd5:  tick = &prescale_cnt[4:0];
      4'd6:  tick = &prescale_cnt[5:0];
      4'd7:  tick = &prescale_cnt[6:0];
      4'd8:  tick = &prescale_cnt[7:0];
      4'd9:  tick = &prescale_cnt[8:0];
      4'd10: tick = &prescale_cnt[9:0];
      default: tick = 1'b1;
    endcase
  end

  always @(posedge C or negedge rst_n) begin
    if (!rst_n) begin
      target0      <= 16'h0000;
      target1      <= 16'h0000;
      count        <= 16'h0000;
      prescale_cnt <= 11'h000;
      conf         <= 7'h00;
      irq0_pending <= 1'b0;
      irq1_pending <= 1'b0;
    end else begin
      if (wr_conf) begin
        conf         <= dOut[6:0];
        prescale_cnt <= 11'h000;
      end

      if (wr_target0)
        target0 <= dOut;

      // Compatibility trick:
      // dOut = 0 or 1 keeps old sync-start function.
      // any other value writes target1.
      if (wr_sync_or_target1) begin
        if (dOut[15:1] == 15'h0000)
          conf[0] <= dOut[0];
        else
          target1 <= dOut;
      end

      if (wr_reset && dOut[0]) begin
        count        <= 16'h0000;
        prescale_cnt <= 11'h000;
        irq0_pending <= 1'b0;
        irq1_pending <= 1'b0;
      end else begin
        if (wr_reset && dOut[1])
          irq0_pending <= 1'b0;
        if (wr_reset && dOut[2])
          irq1_pending <= 1'b0;

        if (timer_en)
          prescale_cnt <= prescale_cnt + 11'd1;

        if (timer_en && !InterLock && tick) begin
          count <= count + 16'd1;

          if (match0)
            irq0_pending <= 1'b1;
          if (match1)
            irq1_pending <= 1'b1;
        end
      end
    end
  end

  assign TimerOut = rd_count   ? count :
                    rd_target0 ? target0 :
                    rd_target1 ? target1 :
                    rd_conf    ? {7'h00, irq1_pending, irq0_pending, conf} :
                    16'h0000;

  assign timer_interrupt = irq_en && !InterLock && (irq0_pending || irq1_pending);

endmodule
