module muxEncoder
  (
    input a,
    input b,
    input c,
    input d,
    output reg [1:0]Q
  );

  always @ (a,b,c,d)
  begin

    Q[0] = | d | b ;
    Q[1] = | d | c ;

  end
endmodule
