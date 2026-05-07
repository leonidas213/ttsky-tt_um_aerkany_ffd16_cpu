import cocotb

from common import wait_execute_steps
from tb_setup import boot_cpu, reset_dut

@cocotb.test()
async def test_cpu_st_ld_absolute(dut):
    dut._log.info("Starting ST/LD absolute test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | 80 34 09 00 ; ldi r0, 0x34
    #  a:0 |    5 | 80 10 2d 00 ; st  0x0010, r0
    #  e:0 |    7 | 80 10 2f 10 ; ld  r1, 0x0010
    # 12:0 |    9 | 3f 11       ; putoutput r1
    # 14:0 |    a |             ; forever:
    # 14:0 |    a | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x8034)
    flash.poke16w(0x0004, 0x0900)
    flash.poke16w(0x0005, 0x8010)
    flash.poke16w(0x0006, 0x2D00)
    flash.poke16w(0x0007, 0x8010)
    flash.poke16w(0x0008, 0x2F10)
    flash.poke16w(0x0009, 0x3F11)
    flash.poke16w(0x000A, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 10, flash)
    assert dut.uo_out.value == 0x34, f"Expected 0x34 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_st_ld_ptr(dut):
    dut._log.info("Starting ST/LD pointer test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #   0:0 |    0 |             ; start:
    #   0:0 |    0 | 3d 02       ; jump main
    #   2:0 |    1 | 00 00       ; nop
    #   4:0 |    2 | 44 00       ; reti
    #   6:0 |    3 |             ; main:
    #   6:0 |    3 | 80 12 09 20 ; ldi r2, 0x0012
    #   a:0 |    5 | 80 56 09 00 ; ldi r0, 0x56
    #   e:0 |    7 | 2b 20       ; st  [r2], r0
    #  10:0 |    8 | 2c 12       ; ld  r1, [r2]
    #  12:0 |    9 | 3f 11       ; putoutput r1
    #  14:0 |    a |             ; forever:
    #  14:0 |    a | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x8012)
    flash.poke16w(0x0004, 0x0920)
    flash.poke16w(0x0005, 0x8056)
    flash.poke16w(0x0006, 0x0900)
    flash.poke16w(0x0007, 0x2B20)
    flash.poke16w(0x0008, 0x2C12)
    flash.poke16w(0x0009, 0x3F11)
    flash.poke16w(0x000A, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 12, flash)
    assert dut.uo_out.value == 0x56, f"Expected 0x56 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_st_ld_offset(dut):
    dut._log.info("Starting ST/LD offset test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | 80 20 09 20 ; ldi r2, 0x0020
    #  a:0 |    5 | 80 77 09 00 ; ldi r0, 0x77
    #  e:0 |    7 | 80 03 31 20 ; st  [r2 + 3], r0
    # 12:0 |    9 | 80 03 32 12 ; ld  r1, [r2 + 3]
    # 16:0 |    b | 3f 11       ; putoutput r1
    # 18:0 |    c |             ; forever:
    # 18:0 |    c | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x8020)
    flash.poke16w(0x0004, 0x0920)
    flash.poke16w(0x0005, 0x8077)
    flash.poke16w(0x0006, 0x0900)
    flash.poke16w(0x0007, 0x8003)
    flash.poke16w(0x0008, 0x3120)
    flash.poke16w(0x0009, 0x8003)
    flash.poke16w(0x000A, 0x3212)
    flash.poke16w(0x000B, 0x3F11)
    flash.poke16w(0x000C, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 12, flash)
    assert dut.uo_out.value == 0x77, f"Expected 0x77 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_mem_addr_zero(dut):
    dut._log.info("Starting RAM addr 0 test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | 80 44 09 00 ; ldi r0, 0x44
    #  a:0 |    5 | 2e 00       ; st  0x0000, r0
    #  c:0 |    6 | 30 10       ; ld  r1, 0x0000
    #  e:0 |    7 | 3f 11       ; putoutput r1
    # 10:0 |    8 |             ; forever:
    # 10:0 |    8 | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x8044)
    flash.poke16w(0x0004, 0x0900)
    flash.poke16w(0x0005, 0x2E00)
    flash.poke16w(0x0006, 0x3010)
    flash.poke16w(0x0007, 0x3F11)
    flash.poke16w(0x0008, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 12, flash)
    assert dut.uo_out.value == 0x44, f"Expected 0x44 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_mem_high_addr(dut):
    dut._log.info("Starting RAM high address test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | 80 66 09 00 ; ldi r0, 0x66
    #  a:0 |    5 | ff ff 2d 10 ; st  0xFFFF, r0
    #  e:0 |    7 | ff ff 2f 11 ; ld  r1, 0xFFFF
    # 12:0 |    9 | 3f 11       ; putoutput r1
    # 14:0 |    a |             ; forever:
    # 14:0 |    a | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x8066)
    flash.poke16w(0x0004, 0x0900)
    flash.poke16w(0x0005, 0xFFFF)
    flash.poke16w(0x0006, 0x2D10)
    flash.poke16w(0x0007, 0xFFFF)
    flash.poke16w(0x0008, 0x2F11)
    flash.poke16w(0x0009, 0x3F11)
    flash.poke16w(0x000A, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 12, flash)
    assert dut.uo_out.value == 0x66, f"Expected 0x66 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_flash_read(dut):
    dut._log.info("Starting flash read test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  2:0 |    1 |             ; start:
    #  2:0 |    1 | 80 02 37 00 ; jumpNotCarry main
    #  6:0 |    3 | 00 00       ; nop
    #  8:0 |    4 | 44 00       ; reti
    #  a:0 |    5 |             ; main:
    #  a:0 |    5 | 80 ff 09 10 ; ldi r1, 0xff
    #  e:0 |    7 |             ; main1:
    #  e:0 |    7 | 45 01       ; ldf r0, [r1]
    # 10:0 |    8 | 3f 10       ; putoutput r0
    # 12:0 |    9 | 0c 11       ; add r1, 1
    # 14:0 |    a | ff fb 39 01 ; jumpNotNegative main1
    # 1fe:0 |   ff |             ; lab:
    # 1fe:0 |   ff | 00 2f       ; 0x2f
    # 200:0 |  100 | 00 13       ; 0x13
    # 202:0 |  101 | 00 b2       ; 0xb2
    # 204:0 |  102 | 00 a4       ; 0xa4
    # 206:0 |  103 | 00 2f       ; 0x2f

    flash.poke16w(0x0000, 0x8002)
    flash.poke16w(0x0001, 0x3700)
    flash.poke16w(0x0002, 0x0000)
    flash.poke16w(0x0003, 0x4400)
    flash.poke16w(0x0004, 0x8100)
    flash.poke16w(0x0005, 0x0910)
    flash.poke16w(0x0006, 0x4501)
    flash.poke16w(0x0007, 0x3F10)
    flash.poke16w(0x0008, 0x0C11)
    flash.poke16w(0x0009, 0xFFFB)
    flash.poke16w(0x000A, 0x3901)
    flash.poke16w(0x00FF, 0x002F)
    flash.poke16w(0x0100, 0x0013)
    flash.poke16w(0x0101, 0x00B2)
    flash.poke16w(0x0102, 0x00A4)
    flash.poke16w(0x0103, 0x002F)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 8, flash)
    assert dut.uo_out.value == 0x2F, f"Expected 0x2F but got {dut.uo_out.value}"
    await wait_execute_steps(dut, 4, flash)
    assert dut.uo_out.value == 0x13, f"Expected 0x13 but got {dut.uo_out.value}"
    await wait_execute_steps(dut, 4, flash)
    assert dut.uo_out.value == 0xB2, f"Expected 0xB2 but got {dut.uo_out.value}"
    await wait_execute_steps(dut, 4, flash)
    assert dut.uo_out.value == 0xA4, f"Expected 0xA4 but got {dut.uo_out.value}"
    await wait_execute_steps(dut, 4, flash)
    assert dut.uo_out.value == 0x2F, f"Expected 0x2F but got {dut.uo_out.value}"
