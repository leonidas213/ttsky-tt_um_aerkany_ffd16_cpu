module Register8
  (
    input [7:0]D,
    input C,
    input en,
    input rst_n,
    output [7:0]Q
  );

  reg [7:0] state ;

  assign Q = state;

  always @ (posedge C or negedge rst_n)
  begin
    if(!rst_n)
    begin
      state <= 8'h0;
    end
    else
      if (en)
        state <= D;


  end
endmodule
