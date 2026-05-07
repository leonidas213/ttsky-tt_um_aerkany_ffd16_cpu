import cocotb

from common import wait_execute_steps
from tb_setup import boot_cpu, reset_dut

@cocotb.test()
async def test_cpu_in_inputreg(dut):
    dut._log.info("Starting IN InputReg test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    dut.ui_in.value = 0x25

    #  0:0 |    0 |       ; start:
    #  0:0 |    0 | 3d 02 ; jump main
    #  2:0 |    1 | 00 00 ; nop
    #  4:0 |    2 | 44 00 ; reti
    #  6:0 |    3 |       ; main:
    #  6:0 |    3 | 42 02 ; in  r0, InputReg
    #  8:0 |    4 | 3f 10 ; putoutput r0
    #  a:0 |    5 |       ; forever:
    #  a:0 |    5 | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x4200)
    flash.poke16w(0x0004, 0x3F10)
    flash.poke16w(0x0005, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    dut.ui_in.value = 0x25
    await wait_execute_steps(dut, 6, flash)
    assert dut.uo_out.value == 0x25, f"Expected 0x25 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_rng_seed_and_read(dut):
    dut._log.info("Starting RNG seed/read test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |                      ; start:
    #  0:0 |    0 | 3d 02                ; jump main
    #  2:0 |    1 | 00 00                ; nop
    #  4:0 |    2 | 44 00                ; reti
    #  6:0 |    3 |                      ; main:
    #  6:0 |    3 | 92 34 09 c0 3f bc    ; RandomSeed 0x1234
    #  c:0 |    6 | 42 0c                ; in  r0, RandomReg
    #  e:0 |    7 | 3f 10                ; putoutput r0
    # 10:0 |    8 |                      ; forever:
    # 10:0 |    8 | 3d ff                ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x9234)
    flash.poke16w(0x0004, 0x09C0)
    flash.poke16w(0x0005, 0x3FBC)
    flash.poke16w(0x0006, 0x420C)
    flash.poke16w(0x0007, 0x3F10)
    flash.poke16w(0x0008, 0x3DFF)
    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 10, flash)
    cocotb.log.info(f"RNG output: {int(dut.uo_out.value):04X}")
    assert int(dut.uo_out.value) > 0

@cocotb.test()
async def test_cpu_rng_changes(dut):
    dut._log.info("Starting RNG change test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |       ; start:
    #  0:0 |    0 | 3d 02 ; jump main
    #  2:0 |    1 | 00 00 ; nop
    #  4:0 |    2 | 44 00 ; reti
    #  6:0 |    3 |       ; main:
    #  6:0 |    3 | 92 34 09 c0 3f bc ; RandomSeed 0x1234
    #  c:0 |    6 | 42 0c ; in  r0, RandomReg
    #  e:0 |    7 | 42 1c ; in  r1, RandomReg
    # 10:0 |    8 | 08 01 ; xor r0, r1
    # 12:0 |    9 | 3f 10 ; putoutput r0
    # 14:0 |    a |       ; forever:
    # 14:0 |    a | 3d ff ; jump forever

    flash.poke16w(0x0000, 0x3D02)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x4400)
    flash.poke16w(0x0003, 0x9234)
    flash.poke16w(0x0004, 0x09C0)
    flash.poke16w(0x0005, 0x3FBC)
    flash.poke16w(0x0006, 0x420C)
    flash.poke16w(0x0007, 0x421C)
    flash.poke16w(0x0008, 0x0801)
    flash.poke16w(0x0009, 0x3F10)
    flash.poke16w(0x000A, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 13, flash)
    assert dut.uo_out.value != 0, "Expected RNG values to differ"

@cocotb.test()
async def test_cpu_timer1_interrupt_basic(dut):
    dut._log.info("Starting timer1 interrupt test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    #  0:0 |    0 |             ; start:
    #  0:0 |    0 | 3d 0d       ; jump main
    #  2:0 |    1 | 00 00       ; nop
    #  4:0 |    2 |             ; interrupt_routine:
    #  4:0 |    2 | 80 77 09 00 ; ldi r0, 0x77
    #  8:0 |    4 | 3f 10       ; putoutput r0
    #  a:0 |    5 | 80 3f 09 20 ; ldi r2, 0b111111
    #  e:0 |    7 | 42 5d       ; in  r5, CpuinterruptEnable
    # 10:0 |    8 | 42 5e       ; in  r5, InputInterruptEnable
    # 12:0 |    9 | 42 5f       ; in  r5, InterruptRegister
    # 14:0 |    a | 3f f2       ; out InterruptRegister, r2
    # 16:0 |    b | 0a 21       ; ldi r2, 0b01
    # 18:0 |    c | 3f 42       ; out timer1Reset, r2
    # 1a:0 |    d | 44 00       ; reti
    # 1c:0 |    e |             ; main:
    # 1c:0 |    e | 0a 21       ; ldi r2, 1
    # 1e:0 |    f | 3f d2       ; out CpuinterruptEnable, r2
    # 20:0 |   10 | 0a 21       ; ldi r2, 0b0001
    # 22:0 |   11 | 3f e2       ; out InputInterruptEnable, r2
    # 24:0 |   12 | 81 ff 09 20 ; ldi r2, 0x01f
    # 28:0 |   14 | 3f 32       ; out timer1Target, r2
    # 2a:0 |   15 | 80 41 09 20 ; ldi r2, 0b1000001
    # 2e:0 |   17 | 3f 22       ; out timer1Config, r2
    # 30:0 |   18 |             ; wait:
    # 30:0 |   18 | 3d ff       ; jump wait

    flash.poke16w(0x0000, 0x3D0D)
    flash.poke16w(0x0001, 0x0000)
    flash.poke16w(0x0002, 0x8077)
    flash.poke16w(0x0003, 0x0900)
    flash.poke16w(0x0004, 0x3F10)
    flash.poke16w(0x0005, 0x803F)
    flash.poke16w(0x0006, 0x0920)
    flash.poke16w(0x0007, 0x425D)
    flash.poke16w(0x0008, 0x425E)
    flash.poke16w(0x0009, 0x425F)
    flash.poke16w(0x000A, 0x3FF2)
    flash.poke16w(0x000B, 0x0A21)
    flash.poke16w(0x000C, 0x3F42)
    flash.poke16w(0x000D, 0x4400)
    flash.poke16w(0x000E, 0x0A21)
    flash.poke16w(0x000F, 0x3FD2)
    flash.poke16w(0x0010, 0x0A21)
    flash.poke16w(0x0011, 0x3FE2)
    flash.poke16w(0x0012, 0x801F)
    flash.poke16w(0x0013, 0x0920)
    flash.poke16w(0x0014, 0x3F32)
    flash.poke16w(0x0015, 0x8041)
    flash.poke16w(0x0016, 0x0920)
    flash.poke16w(0x0017, 0x3F22)
    flash.poke16w(0x0018, 0x3DFF)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 60, flash)
    assert dut.uo_out.value == 0x77, f"Expected 0x77 but got {dut.uo_out.value}"
