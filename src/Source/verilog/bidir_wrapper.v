
// FPGA only
module bidir_wrapper (
    output wire [7:0] data_in,
    input wire  [7:0]  data_out,
    input wire  [7:0]  data_oe,

    inout wire [7:0]  io // bidirectional dont forget to change inout on top level
);
    assign io[0] = data_oe[0] ? data_out[0] : 1'bz;
    assign io[1] = data_oe[1] ? data_out[1] : 1'bz;
    assign io[2] = data_oe[2] ? data_out[2] : 1'bz;
    assign io[3] = data_oe[3] ? data_out[3] : 1'bz;
    assign io[4] = data_oe[4] ? data_out[4] : 1'bz;
    assign io[5] = data_oe[5] ? data_out[5] : 1'bz;
    assign io[6] = data_oe[6] ? data_out[6] : 1'bz;
    assign io[7] = data_oe[7] ? data_out[7] : 1'bz;

    assign data_in = io;


endmodule


