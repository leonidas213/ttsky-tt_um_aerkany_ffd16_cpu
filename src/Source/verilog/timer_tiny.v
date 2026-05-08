module timer_tiny (
    input  [8:0] dOut,
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
    input         execute_pulse,
    output [15:0] TimerOut,
    output        timer_interrupt
  );

  reg [8:0]  target       ;
  reg [8:0]  count        ;
  reg [10:0] prescale_cnt ;
  reg [7:0]  conf         ;

  wire wr_conf   = ioW && (Addr == timerConfigAddr);
  wire wr_target = ioW && (Addr == timerTargetAddr);
  wire wr_reset  = ioW && (Addr == timerResetAddr) && dOut[0];
  wire wr_sync_start = ioW && (Addr == timerSyncStartAddr);

  wire rd_count  = (Addr == timerReadAddr);
  wire rd_target = (Addr == timerTargetAddr);
  wire rd_conf   = (Addr == timerConfigAddr);

  wire       timer_en       = conf[0];
  wire [3:0] prescaler      = conf[4:1];
  wire       auto_reload    = conf[5];
  wire       irq_en         = conf[6];
  wire       source_execute = conf[7];
  wire       target_valid   = (target != 9'h000);
  wire       matched        = target_valid && (count == target);

  // source_execute = 0: prescaler advances every C clock
  // source_execute = 1: prescaler advances only on execute_pulse
  wire source_tick = source_execute ? execute_pulse : 1'b1;

  reg prescale_tick;
  always @(*)
  begin
    case (prescaler)
      4'd0:
        prescale_tick = 1'b1;                  // /1
      4'd1:
        prescale_tick = prescale_cnt[0];       // /2
      4'd2:
        prescale_tick = &prescale_cnt[1:0];    // /4
      4'd3:
        prescale_tick = &prescale_cnt[2:0];    // /8
      4'd4:
        prescale_tick = &prescale_cnt[3:0];    // /16
      4'd5:
        prescale_tick = &prescale_cnt[4:0];    // /32
      4'd6:
        prescale_tick = &prescale_cnt[5:0];    // /64
      4'd7:
        prescale_tick = &prescale_cnt[6:0];    // /128
      4'd8:
        prescale_tick = &prescale_cnt[7:0];    // /256
      4'd9:
        prescale_tick = &prescale_cnt[8:0];    // /512
      4'd10:
        prescale_tick = &prescale_cnt[9:0];    // /1024
      4'd11:
        prescale_tick = &prescale_cnt[10:0];   // /2048
      default:
        prescale_tick = 1'b1;
    endcase
  end

  wire timer_tick = source_tick && prescale_tick;

  always @(posedge C or negedge rst_n)
  begin
    if (!rst_n)
    begin
      target       <= 9'h000;
      count        <= 9'h000;
      prescale_cnt <= 11'h000;
      conf         <= 8'h00;
    end
    else
    begin
      if (wr_conf)
      begin
        conf         <= dOut[7:0];
        prescale_cnt <= 11'h000;
      end

      if (wr_target)
        target <= dOut[8:0];

      if (wr_sync_start)
        conf[0] <= dOut[0];

      if (wr_reset)
      begin
        count        <= 9'h000;
        prescale_cnt <= 11'h000;
        conf         <= 8'h00;
      end
      else
      begin
        if (timer_en && source_tick)
          prescale_cnt <= prescale_cnt + 11'd1;

        if (timer_en && !InterLock)
        begin
          if (matched)
          begin
            if (auto_reload)
              count <= 9'h000;
          end
          else if (timer_tick)
          begin
            count <= count + 9'd1;
          end
        end
      end
    end
  end

  assign TimerOut = rd_count  ? {7'h00, count}  :
                    rd_target ? {7'h00, target} :
                    rd_conf   ? {8'h00, conf}   :
                    16'h0000;

  assign timer_interrupt = irq_en && !InterLock && matched;

endmodule
