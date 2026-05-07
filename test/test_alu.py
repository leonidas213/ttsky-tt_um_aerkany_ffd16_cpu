import cocotb

from common import wait_execute_steps
from tb_setup import boot_cpu, reset_dut

@cocotb.test()
async def test_cpu_add_val(dut):
    dut._log.info("Starting ADD test")
    pins, flash, ram = await boot_cpu(dut)

    flash.trace_fetch = True

    # 0:0 |    0 |       ; start:
    # 0:0 |    0 | 3d 02 ; jump main
    # 2:0 |    1 | 00 00 ; nop
    # 4:0 |    2 |       ; interrupt_routine:
    # 4:0 |    2 | 44 00 ; reti
    # 6:0 |    3 |       ; main:
    # 6:0 |    3 | 0a 05 ; ldi r0 , 5
    # 8:0 |    4 | 0a 12 ; ldi r1 , 2
    # a:0 |    5 | 02 01 ; add r0, r1
    # c:0 |    6 | 3f b0 ; putoutput r0
    # e:0 |    7 |       ; foreverloop:
    # e:0 |    7 | 3d fb ; jump foreverloop
    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A05)
    flash.poke16w(0x0004, 0x0A12)
    flash.poke16w(0x0005, 0x0201)
    flash.poke16w(0x0006, 0x3F10)
    flash.poke16w(0x0007, 0x3DFF)
    for i in range(20):
        prgo = flash.peek8(i)
        dut._log.info("flash[%02x] = %02x", i, prgo)
    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    # Force 'my_register' to stay at 1, regardless of DUT logic
    # dut.tt_um_remedy_cpu.qspi_memory_interface_i19.init_wait_cnt.value = Force(1)
    dut._log.info("Started flash and ram")
    await reset_dut(dut)

    await wait_execute_steps(dut, 9, flash)

    cocotb.log.info("ADD for uo_out is %d", (dut.uo_out.value))
    assert dut.uo_out.value == 7, f"Expected 7 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_mov_reg(dut):
    dut._log.info("Starting MOV test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # 0:0 |    0 |       ; start:
    # 0:0 |    0 | 3d 02 ; jump main
    # 2:0 |    1 | 00 00 ; nop
    # 4:0 |    2 | 44 00 ; reti
    # 6:0 |    3 |       ; main:
    # 6:0 |    3 | 0a 19 ; ldi r1, 9
    # 8:0 |    4 | 01 01 ; mov r0, r1
    # a:0 |    5 | 3f 10 ; putoutput r0
    # c:0 |    6 |       ; forever:
    # c:0 |    6 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A19)
    flash.poke16w(0x0004, 0x0101)
    flash.poke16w(0x0005, 0x3F10)
    flash.poke16w(0x0006, 0x3DFF)
    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 6, flash)
    assert dut.uo_out.value == 9, f"Expected 9 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_add_reg(dut):
    dut._log.info("Starting ADD REG test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # 0:0 |    0 |       ; start:
    # 0:0 |    0 | 3d 02 ; jump main
    # 2:0 |    1 | 00 00 ; nop
    # 4:0 |    2 | 44 00 ; reti
    # 6:0 |    3 |       ; main:
    # 6:0 |    3 | 0a 05 ; ldi r0, 5
    # 8:0 |    4 | 0a 12 ; ldi r1, 2
    # a:0 |    5 | 02 01 ; add r0, r1
    # c:0 |    6 | 3f 10 ; putoutput r0
    # e:0 |    7 |       ; forever:
    # e:0 |    7 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A05)
    flash.poke16w(0x0004, 0x0A12)
    flash.poke16w(0x0005, 0x0201)
    flash.poke16w(0x0006, 0x3F10)
    flash.poke16w(0x0007, 0x3DFF)
    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 7, flash)
    assert dut.uo_out.value == 7, f"Expected 7 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_add_imm4(dut):
    dut._log.info("Starting ADD IMM4 test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # 0:0 |    0 |       ; start:
    # 0:0 |    0 | 3d 02 ; jump main
    # 2:0 |    1 | 00 00 ; nop
    # 4:0 |    2 | 44 00 ; reti
    # 6:0 |    3 |       ; main:
    # 6:0 |    3 | 0a 05 ; ldi r0, 5
    # 8:0 |    4 | 0c 03 ; add r0, 3
    # a:0 |    5 | 3f 10 ; putoutput r0
    # c:0 |    6 |       ; forever:
    # c:0 |    6 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A05)
    flash.poke16w(0x0004, 0x0C03)
    flash.poke16w(0x0005, 0x3F10)
    flash.poke16w(0x0006, 0x3DFF)
    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 6, flash)
    assert dut.uo_out.value == 8, f"Expected 8 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_sub_reg(dut):
    dut._log.info("Starting SUB REG test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # 0:0 |    0 |       ; start:
    # 0:0 |    0 | 3d 02 ; jump main
    # 2:0 |    1 | 00 00 ; nop
    # 4:0 |    2 | 44 00 ; reti
    # 6:0 |    3 |       ; main:
    # 6:0 |    3 | 0a 09 ; ldi r0, 9
    # 8:0 |    4 | 0a 12 ; ldi r1, 2
    # a:0 |    5 | 04 01 ; sub r0, r1
    # c:0 |    6 | 3f 10 ; putoutput r0
    # e:0 |    7 |       ; forever:
    # e:0 |    7 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A09)
    flash.poke16w(0x0004, 0x0A12)
    flash.poke16w(0x0005, 0x0401)
    flash.poke16w(0x0006, 0x3F10)
    flash.poke16w(0x0007, 0x3DFF)
    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 7, flash)
    assert dut.uo_out.value == 7, f"Expected 7 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_and_reg(dut):
    dut._log.info("Starting AND REG test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #   0:0 |    0 |       ; start:
    #   0:0 |    0 | 3d 02 ; jump main
    #   2:0 |    1 | 00 00 ; nop
    #   4:0 |    2 | 44 00 ; reti
    #   6:0 |    3 |       ; main:
    #   6:0 |    3 | 0a 0e ; ldi r0, 14
    #   8:0 |    4 | 0a 1b ; ldi r1, 11
    #   a:0 |    5 | 06 01 ; and r0, r1
    #   c:0 |    6 | 3f 10 ; putoutput r0
    #   e:0 |    7 |       ; forever:
    #   e:0 |    7 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A0E)
    flash.poke16w(0x0004, 0x0A1B)
    flash.poke16w(0x0005, 0x0601)
    flash.poke16w(0x0006, 0x3F10)
    flash.poke16w(0x0007, 0x3DFF)
    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 7, flash)
    assert dut.uo_out.value == 10, f"Expected 10 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_or_reg(dut):
    dut._log.info("Starting OR REG test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |       ; start:
    #  0:0 |    0 | 3d 02 ; jump main
    #  2:0 |    1 | 00 00 ; nop
    #  4:0 |    2 | 44 00 ; reti
    #  6:0 |    3 |       ; main:
    #  6:0 |    3 | 0a 0a ; ldi r0, 10
    #  8:0 |    4 | 0a 15 ; ldi r1, 5
    #  a:0 |    5 | 07 01 ; or  r0, r1
    #  c:0 |    6 | 3f 10 ; putoutput r0
    #  e:0 |    7 |       ; forever:
    #  e:0 |    7 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A0A)
    flash.poke16w(0x0004, 0x0A15)
    flash.poke16w(0x0005, 0x0701)
    flash.poke16w(0x0006, 0x3F10)
    flash.poke16w(0x0007, 0x3DFF)
    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 7, flash)
    assert dut.uo_out.value == 15, f"Expected 15 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_xor_reg(dut):
    dut._log.info("Starting XOR REG test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # 0:0 |    0 |       ; start:
    # 0:0 |    0 | 3d 02 ; jump main
    # 2:0 |    1 | 00 00 ; nop
    # 4:0 |    2 | 44 00 ; reti
    # 6:0 |    3 |       ; main:
    # 6:0 |    3 | 0a 0f ; ldi r0, 15
    # 8:0 |    4 | 0a 1a ; ldi r1, 10
    # a:0 |    5 | 08 01 ; xor r0, r1
    # c:0 |    6 | 3f 10 ; putoutput r0
    # e:0 |    7 |       ; forever:
    # e:0 |    7 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A0F)
    flash.poke16w(0x0004, 0x0A1A)
    flash.poke16w(0x0005, 0x0801)
    flash.poke16w(0x0006, 0x3F10)
    flash.poke16w(0x0007, 0x3DFF)
    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 7, flash)
    assert dut.uo_out.value == 5, f"Expected 5 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_neg(dut):
    dut._log.info("Starting NEG test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # 0:0 |    0 |       ; start:
    # 0:0 |    0 | 3d 02 ; jump main
    # 2:0 |    1 | 00 00 ; nop
    # 4:0 |    2 | 44 00 ; reti
    # 6:0 |    3 |       ; main:
    # 6:0 |    3 | 0a 01 ; ldi r0, 1
    # 8:0 |    4 | 13 00 ; neg r0
    # a:0 |    5 | 3f 10 ; putoutput r0
    # c:0 |    6 |       ; forever:
    # c:0 |    6 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A01)
    flash.poke16w(0x0004, 0x1300)
    flash.poke16w(0x0005, 0x3F10)
    flash.poke16w(0x0006, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 6, flash)
    assert dut.uo_out.value == 255, f"Expected 255 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_not(dut):
    dut._log.info("Starting NOT test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # 0:0 |    0 |       ; start:
    # 0:0 |    0 | 3d 02 ; jump main
    # 2:0 |    1 | 00 00 ; nop
    # 4:0 |    2 | 44 00 ; reti
    # 6:0 |    3 |       ; main:
    # 6:0 |    3 | 0a 00 ; ldi r0, 0
    # 8:0 |    4 | 1a 00 ; not r0
    # a:0 |    5 | 3f 10 ; putoutput r0
    # c:0 |    6 |       ; forever:
    # c:0 |    6 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A00)
    flash.poke16w(0x0004, 0x1A00)
    flash.poke16w(0x0005, 0x3F10)
    flash.poke16w(0x0006, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 6, flash)
    assert dut.uo_out.value == 255, f"Expected 255 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_lsl(dut):
    dut._log.info("Starting LSL test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # 0:0 |    0 |       ; start:
    # 0:0 |    0 | 3d 02 ; jump main
    # 2:0 |    1 | 00 00 ; nop
    # 4:0 |    2 | 44 00 ; reti
    # 6:0 |    3 |       ; main:
    # 6:0 |    3 | 0a 03 ; ldi r0, 3
    # 8:0 |    4 | 24 00 ; lsl r0
    # a:0 |    5 | 3f 10 ; putoutput r0
    # c:0 |    6 |       ; forever:
    # c:0 |    6 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A03)
    flash.poke16w(0x0004, 0x2400)
    flash.poke16w(0x0005, 0x3F10)
    flash.poke16w(0x0006, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 6, flash)
    assert dut.uo_out.value == 6, f"Expected 6 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_lsr(dut):
    dut._log.info("Starting LSR test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # 0:0 |    0 |       ; start:
    # 0:0 |    0 | 3d 02 ; jump main
    # 2:0 |    1 | 00 00 ; nop
    # 4:0 |    2 | 44 00 ; reti
    # 6:0 |    3 |       ; main:
    # 6:0 |    3 | 0a 08 ; ldi r0, 8
    # 8:0 |    4 | 25 00 ; lsr r0
    # a:0 |    5 | 3f 10 ; putoutput r0
    # c:0 |    6 |       ; forever:
    # c:0 |    6 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A08)
    flash.poke16w(0x0004, 0x2500)
    flash.poke16w(0x0005, 0x3F10)
    flash.poke16w(0x0006, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 6, flash)
    assert dut.uo_out.value == 4, f"Expected 4 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_asr(dut):
    dut._log.info("Starting ASR test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | ff fe 09 01 ; ldi r0, -2
    #  a:0 |    5 | 28 00       ; asr r0
    #  c:0 |    6 | 3f 10       ; putoutput r0
    #  e:0 |    7 |             ; forever:
    #  e:0 |    7 | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0xFFFE)
    flash.poke16w(0x0004, 0x0901)
    flash.poke16w(0x0005, 0x2800)
    flash.poke16w(0x0006, 0x3F10)
    flash.poke16w(0x0007, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 8, flash)
    assert dut.uo_out.value == 255, f"Expected 255 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_swap(dut):
    dut._log.info("Starting SWAP test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # 0:0 |    0 |             ; start:
    # 0:0 |    0 | 3d 02       ; jump main
    # 2:0 |    1 | 00 00       ; nop
    # 4:0 |    2 | 44 00       ; reti
    # 6:0 |    3 |             ; main:
    # 6:0 |    3 | 92 34 09 00 ; ldi r0, 0x1234
    # a:0 |    5 | 29 00       ; swap r0
    # c:0 |    6 | 3f 10       ; putoutput r0
    # e:0 |    7 |             ; forever:
    # e:0 |    7 | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x9234)
    flash.poke16w(0x0004, 0x0900)
    flash.poke16w(0x0005, 0x2900)
    flash.poke16w(0x0006, 0x3F10)
    flash.poke16w(0x0007, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 9, flash)
    assert dut.uo_out.value == 0x12, f"Expected 0x12 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_swapn(dut):
    dut._log.info("Starting SWAPN test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # 0:0 |    0 |             ; start:
    # 0:0 |    0 | 3d 02       ; jump main
    # 2:0 |    1 | 00 00       ; nop
    # 4:0 |    2 | 44 00       ; reti
    # 6:0 |    3 |             ; main:
    # 6:0 |    3 | 92 34 09 00 ; ldi r0, 0x1234
    # a:0 |    5 | 2a 00       ; swapn r0
    # c:0 |    6 | 3f 10       ; putoutput r0
    # e:0 |    7 |             ; forever:
    # e:0 |    7 | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x9234)
    flash.poke16w(0x0004, 0x0900)
    flash.poke16w(0x0005, 0x2A00)
    flash.poke16w(0x0006, 0x3F10)
    flash.poke16w(0x0007, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 9, flash)
    assert dut.uo_out.value == 0x43, f"Expected 0x43 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_adc_no_carry_in(dut):
    dut._log.info("Starting ADC no-carry test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #   0:0 |    0 |       ; start:
    #   0:0 |    0 | 3d 02 ; jump main
    #   2:0 |    1 | 00 00 ; nop
    #   4:0 |    2 | 44 00 ; reti
    #   6:0 |    3 |       ; main:
    #   6:0 |    3 | 0a 05 ; ldi r0, 5
    #   8:0 |    4 | 0a 12 ; ldi r1, 2
    #   a:0 |    5 | 1e 22 ; cmp r0, r0
    #   c:0 |    6 | 03 01 ; adc r0, r1
    #   e:0 |    7 | 3f 10 ; putoutput r0
    #  10:0 |    8 |       ; forever:
    #  10:0 |    8 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A05)
    flash.poke16w(0x0004, 0x0A12)
    flash.poke16w(0x0005, 0x1E00)
    flash.poke16w(0x0006, 0x0301)
    flash.poke16w(0x0007, 0x3F10)
    flash.poke16w(0x0008, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 10, flash)
    assert dut.uo_out.value == 7, f"Expected 7 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_adc_with_carry_in(dut):
    dut._log.info("Starting ADC carry-in test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |       ; start:
    #  0:0 |    0 | 3d 02 ; jump main
    #  2:0 |    1 | 00 00 ; nop
    #  4:0 |    2 | 44 00 ; reti
    #  6:0 |    3 |       ; main:
    #  6:0 |    3 | 0a 20 ; ldi r2, 0
    #  8:0 |    4 | 10 21 ; sub r2, 1c
    #  a:0 |    5 | 0a 05 ; ldi r0, 5
    #  c:0 |    6 | 0a 12 ; ldi r1, 2
    #  e:0 |    7 | 03 01 ; adc r0, r1
    # 10:0 |    8 | 3f 10 ; putoutput r0
    # 12:0 |    9 |       ; forever:
    # 12:0 |    9 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A20)
    flash.poke16w(0x0004, 0x1021)
    flash.poke16w(0x0005, 0x0A05)
    flash.poke16w(0x0006, 0x0A12)
    flash.poke16w(0x0007, 0x0301)
    flash.poke16w(0x0008, 0x3F10)
    flash.poke16w(0x0009, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 9, flash)
    assert dut.uo_out.value == 8, f"Expected 8 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_sbc_with_borrow(dut):
    dut._log.info("Starting SBC test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |       ; start:
    #  0:0 |    0 | 3d 02 ; jump main
    #  2:0 |    1 | 00 00 ; nop
    #  4:0 |    2 | 44 00 ; reti
    #  6:0 |    3 |       ; main:
    #  6:0 |    3 | 0a 20 ; ldi r2, 0
    #  8:0 |    4 | 10 21 ; sub r2, 1
    #  a:0 |    5 | 0a 09 ; ldi r0, 9
    #  c:0 |    6 | 0a 12 ; ldi r1, 2
    #  e:0 |    7 | 05 01 ; sbc r0, r1
    # 10:0 |    8 | 3f 10 ; putoutput r0
    # 12:0 |    9 |       ; forever:
    # 12:0 |    9 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A20)
    flash.poke16w(0x0004, 0x1021)
    flash.poke16w(0x0005, 0x0A09)
    flash.poke16w(0x0006, 0x0A12)
    flash.poke16w(0x0007, 0x0501)
    flash.poke16w(0x0008, 0x3F10)
    flash.poke16w(0x0009, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 9, flash)
    assert dut.uo_out.value == 6, f"Expected 6 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_lsl_sets_carry(dut):
    dut._log.info("Starting LSL carry test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | 80 00 09 01 ; ldi r0, 0x8000
    #  a:0 |    5 | 24 00       ; lsl r0
    #  c:0 |    6 | 80 03 34 00 ; jumpCarry carry_label
    # 10:0 |    8 | 0a 11       ; ldi r1, 1
    # 12:0 |    9 | 3f 11       ; putoutput r1
    # 14:0 |    a | 3d 02       ; jump forever
    # 16:0 |    b |             ; carry_label:
    # 16:0 |    b | 0a 15       ; ldi r1, 5
    # 18:0 |    c | 3f 11       ; putoutput r1
    # 1a:0 |    d |             ; forever:
    # 1a:0 |    d | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x8000)
    flash.poke16w(0x0004, 0x0901)
    flash.poke16w(0x0005, 0x2400)
    flash.poke16w(0x0006, 0x8003)
    flash.poke16w(0x0007, 0x3400)
    flash.poke16w(0x0008, 0x0A11)
    flash.poke16w(0x0009, 0x3F11)
    flash.poke16w(0x000A, 0x3D02)
    flash.poke16w(0x000B, 0x0A15)
    flash.poke16w(0x000C, 0x3F11)
    flash.poke16w(0x000D, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 12, flash)
    assert dut.uo_out.value == 5, f"Expected 5 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_lsr_sets_carry(dut):
    dut._log.info("Starting LSR carry test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | 0a 01       ; ldi r0, 1
    #  8:0 |    4 | 25 00       ; lsr r0
    #  a:0 |    5 | 80 03 34 00 ; jumpCarry carry_label
    #  c:0 |    6 | 0a 11       ; ldi r1, 1
    #  e:0 |    7 | 3f 11       ; putoutput r1
    # 10:0 |    8 | 3d 02       ; jump forever
    # 12:0 |    9 |             ; carry_label:
    # 12:0 |    9 | 0a 14       ; ldi r1, 4
    # 14:0 |    a | 3f 11       ; putoutput r1
    # 16:0 |    b |             ; forever:
    # 16:0 |    b | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A01)
    flash.poke16w(0x0004, 0x2500)
    flash.poke16w(0x0005, 0x8003)
    flash.poke16w(0x0006, 0x3400)
    flash.poke16w(0x0007, 0x0A11)
    flash.poke16w(0x0008, 0x3F11)
    flash.poke16w(0x0009, 0x3D02)
    flash.poke16w(0x000A, 0x0A14)
    flash.poke16w(0x000B, 0x3F11)
    flash.poke16w(0x000C, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 9, flash)
    assert dut.uo_out.value == 4, f"Expected 4 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_rol_uses_carry(dut):
    dut._log.info("Starting ROL carry-use test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |       ; start:
    #  0:0 |    0 | 3d 02 ; jump main
    #  2:0 |    1 | 00 00 ; nop
    #  4:0 |    2 | 44 00 ; reti
    #  6:0 |    3 |       ; main:
    #  6:0 |    3 | 0a 20 ; ldi r2, 0
    #  8:0 |    4 | 10 21 ; sub r2, 1
    #  a:0 |    5 | 0a 00 ; ldi r0, 0
    #  c:0 |    6 | 26 00 ; rol r0
    #  e:0 |    7 | 3f 10 ; putoutput r0
    # 10:0 |    8 |       ; forever:
    # 10:0 |    8 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A20)
    flash.poke16w(0x0004, 0x1021)
    flash.poke16w(0x0005, 0x0A00)
    flash.poke16w(0x0006, 0x2600)
    flash.poke16w(0x0007, 0x3F10)
    flash.poke16w(0x0008, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 8, flash)
    assert dut.uo_out.value == 1, f"Expected 1 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_ror_uses_carry(dut):
    dut._log.info("Starting ROR carry-use test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | 0a 20       ; ldi r2, 0
    #  8:0 |    4 | 10 21       ; sub r2, 1
    #  a:0 |    5 | 0a 00       ; ldi r0, 0
    #  c:0 |    6 | 27 00       ; ror r0
    #  e:0 |    7 | 80 03 36 00 ; jumpNegative neg_label
    # 10:0 |    8 | 0a 11       ; ldi r1, 1
    # 12:0 |    9 | 3f 11       ; putoutput r1
    # 14:0 |    a | 3d 02       ; jump forever
    # 16:0 |    b |             ; neg_label:
    # 16:0 |    b | 0a 13       ; ldi r1, 3
    # 18:0 |    c | 3f 11       ; putoutput r1
    # 1a:0 |    d |             ; forever:
    # 1a:0 |    d | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A20)
    flash.poke16w(0x0004, 0x1021)
    flash.poke16w(0x0005, 0x0A00)
    flash.poke16w(0x0006, 0x2700)
    flash.poke16w(0x0007, 0x8003)
    flash.poke16w(0x0008, 0x3600)
    flash.poke16w(0x0009, 0x0A11)
    flash.poke16w(0x000A, 0x3F11)
    flash.poke16w(0x000B, 0x3D02)
    flash.poke16w(0x000C, 0x0A13)
    flash.poke16w(0x000D, 0x3F11)
    flash.poke16w(0x000E, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 14, flash)
    assert dut.uo_out.value == 3, f"Expected 3 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_ldi_i16_positive(dut):
    dut._log.info("Starting LDI i16 positive test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | 92 34 09 00 ; ldi r0, 0x1234
    #  a:0 |    5 | 3f 10       ; putoutput r0
    #  c:0 |    6 |             ; forever:
    #  c:0 |    6 | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x9234)
    flash.poke16w(0x0004, 0x0900)
    flash.poke16w(0x0005, 0x3F10)
    flash.poke16w(0x0006, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 6, flash)
    assert dut.uo_out.value == 0x34, f"Expected 0x34 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_add_i16_negative(dut):
    dut._log.info("Starting ADD i16 negative test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 02       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 | 44 00       ; reti
    #  6:0 |    3 |             ; main:
    #  6:0 |    3 | 0a 05       ; ldi r0, 5
    #  8:0 |    4 | ff fe 0b 01 ; add r0, -2
    #  c:0 |    6 | 3f 10       ; putoutput r0
    #  e:0 |    7 |             ; forever:
    #  e:0 |    7 | 3d ff       ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x0A05)
    flash.poke16w(0x0004, 0xFFFE)
    flash.poke16w(0x0005, 0x0B01)
    flash.poke16w(0x0006, 0x3F10)
    flash.poke16w(0x0007, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 9, flash)
    assert dut.uo_out.value == 3, f"Expected 3 but got {dut.uo_out.value}"
