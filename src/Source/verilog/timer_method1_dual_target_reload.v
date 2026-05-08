module timer (
    input  [15:0] dOut,
    input  [4:0] Addr,
    input         ioW,
    input         C,
    input         InterLock,
    input  [4:0] timerConfigAddr,
    input  [4:0] timerTargetAddr_1,
    input  [4:0] timerTargetAddr_2,
    input  [4:0] timerResetAddr,
    input  [4:0] timerReadAddr,
    input  [4:0] timerSyncStartAddr,
    input         rst_n,
    output [15:0] TimerOut,
    output        timer_interrupt_1,
    output        timer_interrupt_2
  );

  reg [15:0] target0;
  reg [15:0] target1;
  reg [15:0] count;
  reg [10:0] prescale_cnt;
  reg [7:0]  conf;

  wire wr_conf   = ioW && (Addr == timerConfigAddr);
  wire wr_target0 = ioW && (Addr == timerTargetAddr_1);
  wire wr_target1 = ioW && (Addr == timerTargetAddr_2);
  wire wr_reset  = ioW && (Addr == timerResetAddr) && dOut[0];
  wire wr_sync_start = ioW && (Addr == timerSyncStartAddr);

  wire rd_count  = (Addr == timerReadAddr);
  wire rd_target0 = (Addr == timerTargetAddr_1);
  wire rd_target1 = (Addr == timerTargetAddr_2);
  wire rd_conf   = (Addr == timerConfigAddr);

  wire       timer_en     = conf[0];
  wire [3:0] prescaler    = conf[4:1];
  wire       auto_reload_1  = conf[5];
  wire       auto_reload_2  = conf[6];
  wire       irq_en       = conf[7];

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
      conf         <= 8'h00;
    end else begin
      if (wr_conf) begin
        conf         <= dOut[7:0];
        prescale_cnt <= 11'h000;
      end

      if (wr_target0)
        target0 <= dOut;

      // Compatibility trick:
      // dOut = 0 or 1 keeps old sync-start function.
      // any other value writes target1.
      if (wr_sync_start || wr_target1) begin
        if (dOut[15:1] == 15'h0000)
          conf[0] <= dOut[0];
        else
          target1 <= dOut;
      end

      if (wr_reset) begin
        count        <= 16'h0000;
        prescale_cnt <= 11'h000;
        conf         <= 8'h00;
      end else begin
        if (timer_en)
          prescale_cnt <= prescale_cnt + 11'd1;

        if (timer_en && !InterLock) begin
          if (match0) begin
            if (auto_reload_1)
              count <= 16'h0000;
          end else if (match1) begin
            if (auto_reload_2)
              count <= 16'h0000;
          end else if (tick) begin
            count <= count + 16'd1;
          end
        end
      end
    end
  end

  assign TimerOut = rd_count   ? count :
                    rd_target0 ? target0 :
                    rd_target1 ? target1 :
                    rd_conf    ? {8'h00, conf} :
                    16'h0000;

  assign timer_interrupt_1 = irq_en && !InterLock && match0;
  assign timer_interrupt_2 = irq_en && !InterLock && match1;

endmodule
