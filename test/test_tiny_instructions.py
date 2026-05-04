from pathlib import Path


import cocotb
from cocotb.clock import Clock
from cocotb.triggers import with_timeout
from cocotb.triggers import RisingEdge, Timer, ClockCycles
from common import TTPins, clamp_qspi_init_waits, wait_execute_steps
from spimemory import SpiMemoryDevice, SpiFlash, SpiRam, QspiFlash, TTContinuousQSPIFlash


"""i2cCtrl   = 0x10
i2cStatus = 0x11
i2cPresc  = 0x12
i2cData   = 0x13
i2cCmd    = 0x14
I2C_EN        = 0x0001
I2C_IRQ_EN    = 0x0002
I2C_STRETCH   = 0x0004

I2C_BUSY      = 0x0001
I2C_DONE      = 0x0004
I2C_ACK_ERR   = 0x0008
I2C_RX_VALID  = 0x0010
I2C_IRQ_PEND  = 0x0020

I2C_CMD_START = 0x0001
I2C_CMD_STOP  = 0x0002
I2C_CMD_WRITE = 0x0004
I2C_CMD_READ  = 0x0008
I2C_CMD_NACK  = 0x0010"""

"""@cocotb.test()
async def test_cpu_i2c_write_ctrl(dut):
    dut._log.info("Starting CPU I2C ctrl write test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # Assembly:
    # jump main
    # nop
    # reti
    # main:
    #   ldi r0, I2C_EN
    #   out i2cCtrl, r0
    #   in r1, i2cCtrl
    #   putoutput r1
    # forever:
    #   jump forever
    #
    # Expect:
    #   output == I2C_EN

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 8)
    assert dut.uo_out.value == 0x01, f"Expected 0x01 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_i2c_write_prescaler(dut):
    dut._log.info("Starting CPU I2C prescaler write test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # Assembly:
    # jump main
    # nop
    # reti
    # main:
    #   ldi r0, 4
    #   out i2cPresc, r0
    #   in r1, i2cPresc
    #   putoutput r1
    # forever:
    #   jump forever
    #
    # Expect:
    #   output == 4

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 8)
    assert dut.uo_out.value == 4, f"Expected 4 but got {dut.uo_out.value}"
@cocotb.test()
async def test_cpu_i2c_start_stop(dut):
    dut._log.info("Starting CPU I2C start/stop test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # Assembly:
    # jump main
    # nop
    # reti
    # main:
    #   ldi r0, I2C_EN
    #   out i2cCtrl, r0
    #   ldi r0, 0
    #   out i2cPresc, r0
    #   ldi r0, (I2C_CMD_START | I2C_CMD_STOP)
    #   out i2cCmd, r0
    # poll:
    #   in r1, i2cStatus
    #   and r1, I2C_DONE
    #   jumpZero poll
    #   in r2, i2cStatus
    #   putoutput r2
    # forever:
    #   jump forever
    #
    # Expect:
    #   output has DONE bit set

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 40)
    assert int(dut.uo_out.value) != 0, "Expected non-zero status output"

@cocotb.test()
async def test_cpu_i2c_write_ack(dut):
    dut._log.info("Starting CPU I2C write ACK test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # Assembly:
    # jump main
    # nop
    # reti
    # main:
    #   ldi r0, I2C_EN
    #   out i2cCtrl, r0
    #   ldi r0, 0
    #   out i2cPresc, r0
    #   ldi r0, 0xA5
    #   out i2cData, r0
    #   ldi r0, (I2C_CMD_START | I2C_CMD_WRITE | I2C_CMD_STOP)
    #   out i2cCmd, r0
    # poll:
    #   in r1, i2cStatus
    #   and r1, I2C_DONE
    #   jumpZero poll
    #   in r2, i2cStatus
    #   putoutput r2
    # forever:
    #   jump forever
    #
    # Expect:
    #   DONE set, ACK_ERR clear

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    # fake slave should ACK here

    await wait_execute_steps(dut, 50)
    status = int(dut.uo_out.value)
    assert (status & 0x04) != 0, "Expected DONE bit"
    assert (status & 0x08) == 0, "Did not expect ACK_ERR"

@cocotb.test()
async def test_cpu_i2c_write_nack(dut):
    dut._log.info("Starting CPU I2C write NACK test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # Assembly:
    # jump main
    # nop
    # reti
    # main:
    #   ldi r0, I2C_EN
    #   out i2cCtrl, r0
    #   ldi r0, 0
    #   out i2cPresc, r0
    #   ldi r0, 0x5C
    #   out i2cData, r0
    #   ldi r0, (I2C_CMD_START | I2C_CMD_WRITE | I2C_CMD_STOP)
    #   out i2cCmd, r0
    # poll:
    #   in r1, i2cStatus
    #   and r1, I2C_DONE
    #   jumpZero poll
    #   in r2, i2cStatus
    #   putoutput r2
    # forever:
    #   jump forever
    #
    # Expect:
    #   DONE set, ACK_ERR set

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    # fake slave should NACK here

    await wait_execute_steps(dut, 50)
    status = int(dut.uo_out.value)
    assert (status & 0x04) != 0, "Expected DONE bit"
    assert (status & 0x08) != 0, "Expected ACK_ERR"

@cocotb.test()
async def test_cpu_i2c_read_byte(dut):
    dut._log.info("Starting CPU I2C read byte test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # Assembly:
    # jump main
    # nop
    # reti
    # main:
    #   ldi r0, I2C_EN
    #   out i2cCtrl, r0
    #   ldi r0, 0
    #   out i2cPresc, r0
    #   ldi r0, (I2C_CMD_START | I2C_CMD_READ | I2C_CMD_STOP | I2C_CMD_NACK)
    #   out i2cCmd, r0
    # poll:
    #   in r1, i2cStatus
    #   and r1, I2C_RX_VALID
    #   jumpZero poll
    #   in r2, i2cData
    #   putoutput r2
    # forever:
    #   jump forever
    #
    # Expect:
    #   output == slave byte, e.g. 0xA6

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    # fake slave should send 0xA6 here

    await wait_execute_steps(dut, 60)
    assert dut.uo_out.value == 0xA6, f"Expected 0xA6 but got {dut.uo_out.value}"

@cocotb.test()
async def test_cpu_i2c_interrupt_done(dut):
    dut._log.info("Starting CPU I2C interrupt test")
    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # Assembly:
    # jump main
    # nop
    # interrupt_routine:
    #   in r0, InterruptRegister
    #   putoutput r0
    #   ; clear I2C pending bit here
    #   reti
    # main:
    #   ldi r0, (I2C_EN | I2C_IRQ_EN)
    #   out i2cCtrl, r0
    #   ldi r0, 1
    #   out CpuinterruptEnable, r0
    #   ldi r0, 0
    #   out i2cPresc, r0
    #   ldi r0, 0x50
    #   out i2cData, r0
    #   ldi r0, (I2C_CMD_START | I2C_CMD_WRITE | I2C_CMD_STOP)
    #   out i2cCmd, r0
    # idle:
    #   jump idle
    #
    # Expect:
    #   handler runs and output shows interrupt register with I2C bit set

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)

    await wait_execute_steps(dut, 80)
    assert int(dut.uo_out.value) != 0, "Expected interrupt register output"


"""
