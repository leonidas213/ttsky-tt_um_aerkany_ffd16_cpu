import cocotb

from common import wait_execute_steps
from tb_setup import boot_cpu, reset_dut

@cocotb.test()
async def test_cpu_cmp_jumpzero(dut):
    dut._log.info("Starting CMP/JZ test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #   0:0 |    0 |             ; start:
    #   0:0 |    0 | 3d 02       ; jump main
    #   2:0 |    1 | 00 00       ; nop
    #   4:0 |    2 | 44 00       ; reti
    #   6:0 |    3 |             ; main:
    #   6:0 |    3 | 0a 05       ; ldi r0, 5
    #   8:0 |    4 | 0a 15       ; ldi r1, 5
    #   a:0 |    5 | 1e 01       ; cmp r0, r1
    #   c:0 |    6 | 80 03 35 00 ; jumpZero equal_label
    #   e:0 |    7 | 0a 21       ; ldi r2, 1
    #  10:0 |    8 | 3f 12       ; putoutput r2
    #  12:0 |    9 | 3d 02       ; jump forever
    #  14:0 |    a |             ; equal_label:
    #  14:0 |    a | 0a 29       ; ldi r2, 9
    #  16:0 |    b | 3f 12       ; putoutput r2
    #  18:0 |    c |             ; forever:
    #  18:0 |    c | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A05)
    flash.poke16w(0x0004, 0x0A15)
    flash.poke16w(0x0005, 0x1E01)
    flash.poke16w(0x0006, 0x8003)
    flash.poke16w(0x0007, 0x3500)
    flash.poke16w(0x0008, 0x0A21)
    flash.poke16w(0x0009, 0x3F12)
    flash.poke16w(0x000A, 0x3D02)
    flash.poke16w(0x000B, 0x0A29)
    flash.poke16w(0x000C, 0x3F12)
    flash.poke16w(0x000D, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 10, flash)
    assert dut.uo_out.value == 9, f"Expected 9 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_cmp_jumpnotzero(dut):
    dut._log.info("Starting CMP/JNZ test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #   0:0 |    0 |             ; start:
    #   0:0 |    0 | 3d 02       ; jump main
    #   2:0 |    1 | 00 00       ; nop
    #   4:0 |    2 | 44 00       ; reti
    #   6:0 |    3 |             ; main:
    #   6:0 |    3 | 0a 05       ; ldi r0, 5
    #   8:0 |    4 | 0a 14       ; ldi r1, 4
    #   a:0 |    5 | 1e 01       ; cmp r0, r1
    #   c:0 |    6 | 80 03 38 00 ; jumpNotZero noteq_label
    #   e:0 |    7 | 0a 21       ; ldi r2, 1
    #  10:0 |    8 | 3f 12       ; putoutput r2
    #  12:0 |    9 | 3d 02       ; jump forever
    #  14:0 |    a |             ; noteq_label:
    #  14:0 |    a | 0a 28       ; ldi r2, 8
    #  16:0 |    b | 3f 12       ; putoutput r2
    #  18:0 |    c |             ; forever:
    #  18:0 |    c | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A05)
    flash.poke16w(0x0004, 0x0A14)
    flash.poke16w(0x0005, 0x1E01)
    flash.poke16w(0x0006, 0x8003)
    flash.poke16w(0x0007, 0x3800)
    flash.poke16w(0x0008, 0x0A21)
    flash.poke16w(0x0009, 0x3F12)
    flash.poke16w(0x000A, 0x3D02)
    flash.poke16w(0x000B, 0x0A28)
    flash.poke16w(0x000C, 0x3F12)
    flash.poke16w(0x000D, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 10, flash)
    assert dut.uo_out.value == 8, f"Expected 8 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_jump_abs(dut):
    dut._log.info("Starting ABS JUMP test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #   0:0 |    0 |             ; start:
    #   0:0 |    0 | 80 ff 3c 00 ; jump main
    #                            ; #addr 0xff <-- this  put assembly next to the address
    # 1fe:0 |   ff |             ; main:
    # 1fe:0 |   ff | 0a 0c       ; ldi r0, 12
    # 200:0 |  100 | 3f 10       ; putoutput r0
    # 202:0 |  101 |             ; forever:
    # 202:0 |  101 | 82 ff 3c 00 ; jump jumplabel
    #                            ; #addr 0x02ff <-- this  put assembly next to the address
    # 5fe:0 |  2ff |             ; jumplabel:
    # 5fe:0 |  2ff | 81 01 3c 00 ; jump forever

    flash.poke16w(0x0000, 0x80FF)
    flash.poke16w(0x0001, 0x3C00)
    flash.poke16w(0x00FF, 0x0A0C)
    flash.poke16w(0x0100, 0x3F10)
    flash.poke16w(0x0101, 0x82FF)
    flash.poke16w(0x0102, 0x3C00)
    flash.poke16w(0x02FF, 0x8101)
    flash.poke16w(0x0300, 0x3C00)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 9, flash)
    assert dut.uo_out.value == 12, f"Expected 12 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_jumpzero_taken(dut):
    dut._log.info("Starting JZ taken test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | 0a 05       ; ldi r0, 5
    #  8:0 |    4 | 21 05       ; cmp r0, 5
    #  a:0 |    5 | 80 03 35 00 ; jumpZero equal_label
    #  e:0 |    7 | 0a 11       ; ldi r1, 1
    # 10:0 |    8 | 3f 11       ; putoutput r1
    # 12:0 |    9 | 3d 02       ; jump forever
    # 14:0 |    a |             ; equal_label:
    # 14:0 |    a | 0a 19       ; ldi r1, 9
    # 16:0 |    b | 3f 11       ; putoutput r1
    # 18:0 |    c |             ; forever:
    # 18:0 |    c | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A05)
    flash.poke16w(0x0004, 0x2105)
    flash.poke16w(0x0005, 0x8003)   
    flash.poke16w(0x0006, 0x3500)
    flash.poke16w(0x0007, 0x0A11)
    flash.poke16w(0x0008, 0x3F11)
    flash.poke16w(0x0009, 0x3D02)
    flash.poke16w(0x000A, 0x0A19)
    flash.poke16w(0x000B, 0x3F11)
    flash.poke16w(0x000C, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 12, flash)
    assert dut.uo_out.value == 9, f"Expected 9 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_jumpnotzero_taken(dut):
    dut._log.info("Starting JNZ taken test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | 0a 05       ; ldi r0, 5
    #  8:0 |    4 | 21 04       ; cmp r0, 4
    #  a:0 |    5 | 80 03 38 00 ; jumpNotZero noteq_label
    #  e:0 |    7 | 0a 11       ; ldi r1, 1
    # 10:0 |    8 | 3f 11       ; putoutput r1
    # 12:0 |    9 | 3d 02       ; jump forever
    # 14:0 |    a |             ; noteq_label:
    # 14:0 |    a | 0a 18       ; ldi r1, 8
    # 16:0 |    b | 3f 11       ; putoutput r1
    # 18:0 |    c |             ; forever:
    # 18:0 |    c | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A05)
    flash.poke16w(0x0004, 0x2104)
    flash.poke16w(0x0005, 0x8003)
    flash.poke16w(0x0006, 0x3800)
    flash.poke16w(0x0007, 0x0A11)
    flash.poke16w(0x0008, 0x3F11)
    flash.poke16w(0x0009, 0x3D02)
    flash.poke16w(0x000A, 0x0A18)
    flash.poke16w(0x000B, 0x3F11)
    flash.poke16w(0x000C, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 10, flash)
    assert dut.uo_out.value == 8, f"Expected 8 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_jumpnegative_taken(dut):
    dut._log.info("Starting JN taken test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | 0a 01       ; ldi r0, 1
    #  8:0 |    4 | 21 02       ; cmp r0, 2
    #  a:0 |    5 | 80 03 36 00 ; jumpNegative neg_label
    #  e:0 |    7 | 0a 11       ; ldi r1, 1
    # 10:0 |    8 | 3f 11       ; putoutput r1
    # 12:0 |    9 | 3d 02       ; jump forever
    # 14:0 |    a |             ; neg_label:
    # 14:0 |    a | 0a 17       ; ldi r1, 7
    # 16:0 |    b | 3f 11       ; putoutput r1
    # 18:0 |    c |             ; forever:
    # 18:0 |    c | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A01)
    flash.poke16w(0x0004, 0x2102)
    flash.poke16w(0x0005, 0x8003)
    flash.poke16w(0x0006, 0x3600)
    flash.poke16w(0x0007, 0x0A11)
    flash.poke16w(0x0008, 0x3F11)
    flash.poke16w(0x0009, 0x3D02)
    flash.poke16w(0x000A, 0x0A17)
    flash.poke16w(0x000B, 0x3F11)
    flash.poke16w(0x000C, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 10, flash)
    assert dut.uo_out.value == 7, f"Expected 7 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_jumpcarry_taken(dut):
    dut._log.info("Starting JC taken test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | ff ff 09 01 ; ldi r0, 0xFFFF
    #  a:0 |    5 | 0c 01       ; add r0, 1
    #  c:0 |    6 | 80 03 34 00 ; jumpCarry carry_label
    # 10:0 |    8 | 0a 11       ; ldi r1, 1
    # 12:0 |    9 | 3f 11       ; putoutput r1
    # 14:0 |    a | 3d 02       ; jump forever
    # 16:0 |    b |             ; carry_label:
    # 16:0 |    b | 0a 16       ; ldi r1, 6
    # 18:0 |    c | 3f 11       ; putoutput r1
    # 1a:0 |    d |             ; forever:
    # 1a:0 |    d | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0xFFFF)
    flash.poke16w(0x0004, 0x0901)
    flash.poke16w(0x0005, 0x0C01)
    flash.poke16w(0x0006, 0x8003)
    flash.poke16w(0x0007, 0x3400)
    flash.poke16w(0x0008, 0x0A11)
    flash.poke16w(0x0009, 0x3F11)
    flash.poke16w(0x000A, 0x3D02)
    flash.poke16w(0x000B, 0x0A16)
    flash.poke16w(0x000C, 0x3F11)
    flash.poke16w(0x000D, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 10, flash)
    assert dut.uo_out.value == 6, f"Expected 6 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_countdown_loop(dut):
    dut._log.info("Starting countdown loop test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |       ; start:
    #  0:0 |    0 | 3d 02 ; jump main
    #  2:0 |    1 | 00 00 ; nop
    #  4:0 |    2 | 44 00 ; reti
    #  6:0 |    3 |       ; main:
    #  6:0 |    3 | 0a 05 ; ldi r0, 5
    #  8:0 |    4 |       ; loop:
    #  8:0 |    4 | 10 01 ; sub r0, 1
    #  a:0 |    5 | 38 fe ; jumpNotZero loop
    #  c:0 |    6 | 3f 10 ; putoutput r0
    #  e:0 |    7 |       ; forever:
    #  e:0 |    7 | 3d ff ; jump foreve

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A05)
    flash.poke16w(0x0004, 0x1001)
    flash.poke16w(0x0005, 0x38FE)
    flash.poke16w(0x0006, 0x3F10)
    flash.poke16w(0x0007, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 20, flash)
    assert dut.uo_out.value == 0, f"Expected 0 but got {dut.uo_out.value}"
