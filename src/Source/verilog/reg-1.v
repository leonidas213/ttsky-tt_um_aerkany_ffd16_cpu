module Register1
  (
    input D,
    input C,
    input en,
    input rst_n,
    output Q
  );

  reg  state;

  assign Q = state;

  always @ (negedge C, negedge rst_n)
  begin

    if(!rst_n)
    begin
      state <= 1'h0;
    end
    else
      if (en)
        state <= D;

  end
endmodule
