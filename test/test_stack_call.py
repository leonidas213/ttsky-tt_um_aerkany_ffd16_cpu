import cocotb

from common import wait_execute_steps
from tb_setup import boot_cpu, reset_dut

@cocotb.test()
async def test_cpu_rcall_rret(dut):
    dut._log.info("Starting RCALL/RRET test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 | 00 00       ; nop
    #  2:0 |    1 |             ; start:
    #  2:0 |    1 | 3d 04       ; jump main
    #  4:0 |    2 | 00 00       ; nop
    #  6:0 |    3 | 44 00       ; reti
    #  8:0 |    4 |             ; func:
    #  8:0 |    4 | 0a 0b       ; ldi r0, 11
    #  a:0 |    5 | 3b 0f       ; rret RA
    #  c:0 |    6 |             ; main:
    #  c:0 |    6 | 80 04 3a f0 ; rcall RA, func
    # 10:0 |    8 | 3f 10       ; putoutput r0
    # 12:0 |    9 |             ; forever:
    # 12:0 |    9 | 3d ff       ; jump forever
    #

    flash.poke16w(0x0000, 0x3D04)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A0B)
    flash.poke16w(0x0004, 0x3B0F)
    flash.poke16w(0x0005, 0x8004)
    flash.poke16w(0x0006, 0x3AF0)
    flash.poke16w(0x0007, 0x3F10)
    flash.poke16w(0x0008, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 14, flash)
    assert dut.uo_out.value == 11, f"Expected 11 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_push_pop_basic(dut):
    dut._log.info("Starting PUSH/POP basic test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | 81 00 09 e0 ; ldi SP, 0x0100
    #  a:0 |    5 | 80 34 09 00 ; ldi r0, 0x34
    #  e:0 |    7 | 10 e1 2b e0 ; push r0
    # 12:0 |    9 | 0a 00       ; zero r0
    # 14:0 |    a | 2c 1e 0c e1 ; pop r1
    # 18:0 |    c | 3f 11       ; putoutput r1
    # 1a:0 |    d |             ; forever:
    # 1a:0 |    d | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x8100)
    flash.poke16w(0x0004, 0x09E0)
    flash.poke16w(0x0005, 0x8034)
    flash.poke16w(0x0006, 0x0900)
    flash.poke16w(0x0007, 0x10E1)
    flash.poke16w(0x0008, 0x2BE0)
    flash.poke16w(0x0009, 0x0A00)
    flash.poke16w(0x000A, 0x2C1E)
    flash.poke16w(0x000B, 0x0CE1)
    flash.poke16w(0x000C, 0x3F11)
    flash.poke16w(0x000D, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 15, flash)
    assert dut.uo_out.value == 0x34, f"Expected 0x34 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_push_pop_lifo(dut):
    dut._log.info("Starting PUSH/POP LIFO test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | ff ff 09 e1 ; ldi SP, 0xffff
    #  a:0 |    5 | 80 11 09 00 ; ldi r0, 0x11
    #  e:0 |    7 | 80 22 09 10 ; ldi r1, 0x22
    # 12:0 |    9 | 80 10 09 20 ; ldi r2 , 0x10
    # 16:0 |    b | 10 e1 2b e0 ; push r0
    # 1a:0 |    d | 10 e1 2b e1 ; push r1
    # 1e:0 |    f | 2c 2e 0c e1 ; pop r2
    # 22:0 |   11 | 2c 3e 0c e1 ; pop r3
    # 26:0 |   13 | 3f 12       ; putoutput r2
    # 28:0 |   14 |             ; forever:
    # 28:0 |   14 | 80 14 3c 00 ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0xFFFF)
    flash.poke16w(0x0004, 0x09E1)
    flash.poke16w(0x0005, 0x8011)
    flash.poke16w(0x0006, 0x0900)
    flash.poke16w(0x0007, 0x8022)
    flash.poke16w(0x0008, 0x0910)
    flash.poke16w(0x0009, 0x8010)
    flash.poke16w(0x000A, 0x0920)
    flash.poke16w(0x000B, 0x10E1)
    flash.poke16w(0x000C, 0x2BE0)
    flash.poke16w(0x000D, 0x10E1)
    flash.poke16w(0x000E, 0x2BE1)
    flash.poke16w(0x000F, 0x2C2E)
    flash.poke16w(0x0010, 0x0CE1)
    flash.poke16w(0x0011, 0x2C3E)
    flash.poke16w(0x0012, 0x0CE1)
    flash.poke16w(0x0013, 0x3F12)
    flash.poke16w(0x0014, 0x8014)
    flash.poke16w(0x0015, 0x3C00)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 25, flash)
    assert dut.uo_out.value == 0x22, f"Expected 0x22 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_push_pop_lifo_second_value(dut):
    dut._log.info("Starting PUSH/POP second value test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | 81 00 09 e0 ; ldi SP, 0x0100
    #  a:0 |    5 | 80 11 09 00 ; ldi r0, 0x11
    #  e:0 |    7 | 80 22 09 10 ; ldi r1, 0x22
    # 12:0 |    9 | 10 e1 2b e0 ; push r0
    # 16:0 |    b | 10 e1 2b e1 ; push r1
    # 1a:0 |    d | 2c 2e 0c e1 ; pop r2
    # 1e:0 |    f | 2c 3e 0c e1 ; pop r3
    # 22:0 |   11 | 3f 13       ; putoutput r3
    # 24:0 |   12 |             ; forever:
    # 24:0 |   12 | 80 12 3c 00 ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x8100)
    flash.poke16w(0x0004, 0x09E0)
    flash.poke16w(0x0005, 0x8011)
    flash.poke16w(0x0006, 0x0900)
    flash.poke16w(0x0007, 0x8022)
    flash.poke16w(0x0008, 0x0910)
    flash.poke16w(0x0009, 0x10E1)
    flash.poke16w(0x000A, 0x2BE0)
    flash.poke16w(0x000B, 0x10E1)
    flash.poke16w(0x000C, 0x2BE1)
    flash.poke16w(0x000D, 0x2C2E)
    flash.poke16w(0x000E, 0x0CE1)
    flash.poke16w(0x000F, 0x2C3E)
    flash.poke16w(0x0010, 0x0CE1)
    flash.poke16w(0x0011, 0x3F13)
    flash.poke16w(0x0012, 0x8012)
    flash.poke16w(0x0013, 0x3C00)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 25, flash)
    assert dut.uo_out.value == 0x11, f"Expected 0x11 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_rcall_rret_basic(dut):
    dut._log.info("Starting RCALL/RRET basic test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 05       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; func:
    #  6:0 |    3 | 80 55 09 00 ; ldi r0, 0x55
    #  a:0 |    5 | 3b 0f       ; rret RA
    #  c:0 |    6 |             ; main:
    #  c:0 |    6 | 80 04 3a f0 ; rcall RA, func
    # 10:0 |    8 | 3f 10       ; putoutput r0
    # 12:0 |    9 |             ; forever:
    # 12:0 |    9 | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D05)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x8055)
    flash.poke16w(0x0004, 0x0900)
    flash.poke16w(0x0005, 0x3B0F)
    flash.poke16w(0x0006, 0x8004)
    flash.poke16w(0x0007, 0x3AF0)
    flash.poke16w(0x0008, 0x3F10)
    flash.poke16w(0x0009, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 14, flash)
    assert dut.uo_out.value == 0x55, f"Expected 0x55 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_call_macro_basic(dut):
    dut._log.info("Starting CALL macro test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 07       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; func:
    #  6:0 |    3 | 80 66 09 00 ; ldi r0, 0x66
    #  a:0 |    5 | 2c fe 0c e1 3b 0f ; ret 0
    # 10:0 |    8 |             ; main:
    # 10:0 |    8 | 81 00 09 e0 ; ldi SP, 0x0100
    # 14:0 |    a | 10 e1 80 11 09 f0 2b ef 80 04 3c 00 ; call func
    # 20:0 |   10 | 3f 10       ; putoutput r0
    # 22:0 |   11 |             ; forever:
    # 22:0 |   11 | 80 11 3c 00 ; jump forever

    flash.poke16w(0x0000, 0x3D07)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x8066)
    flash.poke16w(0x0004, 0x0900)
    flash.poke16w(0x0005, 0x2CFE)
    flash.poke16w(0x0006, 0x0CE1)
    flash.poke16w(0x0007, 0x3B0F)
    flash.poke16w(0x0008, 0x8100)
    flash.poke16w(0x0009, 0x09E0)
    flash.poke16w(0x000A, 0x10E1)
    flash.poke16w(0x000B, 0x8011)
    flash.poke16w(0x000C, 0x09F0)
    flash.poke16w(0x000D, 0x2BEF)
    flash.poke16w(0x000E, 0x8004)
    flash.poke16w(0x000F, 0x3C00)
    flash.poke16w(0x0010, 0x3F10)
    flash.poke16w(0x0011, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 17, flash)
    assert dut.uo_out.value == 0x66, f"Expected 0x66 but got {dut.uo_out.value}"

async def test_cpu_call_ret_cleanup(dut):
    dut._log.info("Starting CALL/RET cleanup test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |                   ; start:
    #  0:0 |    0 | 3d 07             ; jump main
    #  2:0 |    1 | 00 00             ; nop
    #  4:0 |    2 | 44 00             ; reti
    #  6:0 |    3 |                   ; func:
    #  6:0 |    3 | 80 44 09 00       ; ldi r0, 0x44
    #  a:0 |    5 | 2c fe 0c e2 3b 0f ; ret 1
    # 10:0 |    8 |                   ; main:
    # 10:0 |    8 | 81 00 09 e0       ; ldi SP, 0x0100
    # 14:0 |    a | 10 e1 2b e2       ; push r2
    # 18:0 |    c | 10 e1 80 13 09 f0 2b ef 80 04 3c 00 ; call func
    # 24:0 |   12 | 10 e1 2b e0       ; push r0
    # 28:0 |   14 | 2c 1e 0c e1       ; pop r1
    # 2c:0 |   16 | 3f 11             ; putoutput r1
    # 2e:0 |   17 |                   ; forever:
    # 2e:0 |   17 | 80 17 3c 00       ; jump forever

    flash.poke16w(0x0000, 0x3D07)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x8044)
    flash.poke16w(0x0004, 0x0900)
    flash.poke16w(0x0005, 0x2CFE)
    flash.poke16w(0x0006, 0x0CE2)
    flash.poke16w(0x0007, 0x3B0F)
    flash.poke16w(0x0008, 0x8100)
    flash.poke16w(0x0009, 0x09E0)
    flash.poke16w(0x000A, 0x10E1)
    flash.poke16w(0x000B, 0x8013)
    flash.poke16w(0x000C, 0x09F0)
    flash.poke16w(0x000D, 0x2BEF)
    flash.poke16w(0x000E, 0x8004)
    flash.poke16w(0x000F, 0x3C00)
    flash.poke16w(0x0010, 0x10E1)
    flash.poke16w(0x0011, 0x2BE0)
    flash.poke16w(0x0012, 0x2C1E)
    flash.poke16w(0x0013, 0x0CE1)
    flash.poke16w(0x0014, 0x3F11)
    flash.poke16w(0x0015, 0x8017)
    flash.poke16w(0x0016, 0x3C00)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 15, flash)
    assert dut.uo_out.value == 0x44, f"Expected 0x44 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_enter_leave_basic(dut):
    dut._log.info("Starting ENTER/LEAVE basic test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True
    #  0:0 |    0 |             ; nop    
    #  2:0 |    1 |             ; start:
    #  2:0 |    1 | 3d 0e       ; jump main
    #  4:0 |    2 | 00 00       ; nop
    #  6:0 |    3 | 44 00       ; reti
    #  8:0 |    4 |             ; func:
    #  8:0 |    4 | 10 e1 2b ed 01 de 10 e2 ; enter 2
    # 10:0 |    8 | 80 21 09 00 ; ldi r0, 0x21
    # 14:0 |    a | 01 ed 2c de 0c e1 ; leave
    # 1a:0 |    d | 2c fe 0c e1 3b 0f ; ret 0
    # 20:0 |   10 |             ; main:
    # 20:0 |   10 | 81 00 09 e0 ; ldi SP, 0x0100
    # 24:0 |   12 | 10 e1 80 18 09 f0 2b ef 80 04 3c 00 ; call func
    # 30:0 |   18 | 3f 10       ; putoutput r0
    # 32:0 |   19 |             ; forever:
    # 32:0 |   19 | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3d0e)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x10e1)
    flash.poke16w(0x0004, 0x2bed)
    flash.poke16w(0x0005, 0x01de)
    flash.poke16w(0x0006, 0x10e2)
    flash.poke16w(0x0007, 0x8021)
    flash.poke16w(0x0008, 0x0900)
    flash.poke16w(0x0009, 0x01ed)
    flash.poke16w(0x000A, 0x2cde)
    flash.poke16w(0x000B, 0x0ce1)
    flash.poke16w(0x000C, 0x2cfe)
    flash.poke16w(0x000D, 0x0ce1)
    flash.poke16w(0x000E, 0x3b0f)
    flash.poke16w(0x000F, 0x8100)
    flash.poke16w(0x0010, 0x09e0)
    flash.poke16w(0x0011, 0x10e1)
    flash.poke16w(0x0012, 0x8018)
    flash.poke16w(0x0013, 0x09f0)
    flash.poke16w(0x0014, 0x2bef)
    flash.poke16w(0x0015, 0x8004)
    flash.poke16w(0x0016, 0x3c00)
    flash.poke16w(0x0017, 0x3f10)
    flash.poke16w(0x0018, 0x3dff)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 25, flash)
    assert dut.uo_out.value == 0x21, f"Expected 0x21 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_bp_local_access_style(dut):
    dut._log.info("Starting BP local access style test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  2:0 |    1 |             ; start:
    #  2:0 |    1 | 3d 13       ; jump main
    #  4:0 |    2 | 00 00       ; nop
    #  6:0 |    3 | 44 00       ; reti
    #  8:0 |    4 |             ; func:
    #  8:0 |    4 | 10 e1 2b ed 01 de 10 e2 ; enter 2
    # 10:0 |    8 | 80 5a 09 00 ; ldi r0, 0x5A
    # 14:0 |    a | ff ff 31 d0 ; st  [BP - 1], r0
    # 18:0 |    c | ff ff 32 1d ; ld  r1, [BP - 1]
    # 1c:0 |    e | 3f 11       ; putoutput r1
    # 1e:0 |    f | 01 ed 2c de 0c e1 ; leave
    # 24:0 |   12 | 2c fe 0c e1 3b 0f ; ret 0
    # 2a:0 |   15 |             ; main:
    # 2a:0 |   15 | 81 00 09 e0 ; ldi SP, 0x0100
    # 2e:0 |   17 | 10 e1 80 1d 09 f0 2b ef 80 04 3c 00 ; call func
    # 3a:0 |   1d |             ; forever:
    # 3a:0 |   1d | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3d13)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x10e1)
    flash.poke16w(0x0004, 0x2bed)
    flash.poke16w(0x0005, 0x01de)
    flash.poke16w(0x0006, 0x10e2)
    flash.poke16w(0x0007, 0x805a)
    flash.poke16w(0x0008, 0x0900)
    flash.poke16w(0x0009, 0xffff)
    flash.poke16w(0x000A, 0x31d0)
    flash.poke16w(0x000B, 0xffff)
    flash.poke16w(0x000C, 0x321d)
    flash.poke16w(0x000D, 0x0ce1)
    flash.poke16w(0x000E, 0x3f11)
    flash.poke16w(0x000F, 0x01ed)
    flash.poke16w(0x0010, 0x2cde)
    flash.poke16w(0x0011, 0x0ce1)
    flash.poke16w(0x0012, 0x2cfe)
    flash.poke16w(0x0013, 0x0ce1)
    flash.poke16w(0x0014, 0x3b0f)
    flash.poke16w(0x0015, 0x8100)
    flash.poke16w(0x0016, 0x09e0)
    flash.poke16w(0x0017, 0x10e1)
    flash.poke16w(0x0018, 0x801d)
    flash.poke16w(0x0019, 0x09f0)
    flash.poke16w(0x001A, 0x2bef)
    flash.poke16w(0x001B, 0x8004)
    flash.poke16w(0x001C, 0x3c00)
    flash.poke16w(0x001D, 0x3f10)
    flash.poke16w(0x001E, 0x3dff)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 36, flash)
    assert dut.uo_out.value == 0x5A, f"Expected 0x5A but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_scall_macro(dut):
    dut._log.info("Starting _SCALL macro test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 05       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; func:
    #  6:0 |    3 | 80 2b 09 00 ; ldi r0, 0x2B
    #  a:0 |    5 | 3b 0f       ; rret RA
    #  c:0 |    6 |             ; main:
    #  c:0 |    6 | 81 00 09 e0 ; ldi SP, 0x0100
    # 10:0 |    8 | 10 e1 2b ef 80 04 3a f0 2c fe 0c e1 ; _scall func
    # 1c:0 |    e | 3f 10       ; putoutput r0
    # 1e:0 |    f |             ; forever:
    # 1e:0 |    f | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D05)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x802B)
    flash.poke16w(0x0004, 0x0900)
    flash.poke16w(0x0005, 0x3B0F)
    flash.poke16w(0x0006, 0x8100)
    flash.poke16w(0x0007, 0x09E0)
    flash.poke16w(0x0008, 0x10E1)
    flash.poke16w(0x0009, 0x2BEF)
    flash.poke16w(0x000A, 0x8004)
    flash.poke16w(0x000B, 0x3AF0)
    flash.poke16w(0x000C, 0x2CFE)
    flash.poke16w(0x000D, 0x0CE1)
    flash.poke16w(0x000E, 0x3F10)
    flash.poke16w(0x000F, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 20, flash)
    assert dut.uo_out.value == 0x2B, f"Expected 0x2B but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_push_writes_stack_memory(dut):
    dut._log.info("Starting PUSH RAM write test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | 81 00 09 e0 ; ldi SP, 0x0100
    #  a:0 |    5 | 80 4d 09 00 ; ldi r0, 0x4D
    #  e:0 |    7 | 10 e1 2b e0 ; push r0
    # 12:0 |    9 | 3f 10       ; putoutput r0
    # 14:0 |    a |             ; forever:
    # 14:0 |    a | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x8100)
    flash.poke16w(0x0004, 0x09E0)
    flash.poke16w(0x0005, 0x804D)
    flash.poke16w(0x0006, 0x0900)
    flash.poke16w(0x0007, 0x10E1)
    flash.poke16w(0x0008, 0x2BE0)
    flash.poke16w(0x0009, 0x3F10)
    flash.poke16w(0x000A, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 12, flash)

    assert dut.uo_out.value == 0x4D, f"Expected 0x4D but got {dut.uo_out.value}"
