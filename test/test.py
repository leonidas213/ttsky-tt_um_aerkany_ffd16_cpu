from pathlib import Path
from collections import deque

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ClockCycles
from common import TTPins
from spimemory import SpiMemoryDevice, SpiFlash, SpiRam, QspiFlash


async def reset_dut(dut):
    dut.rst_n.value = 0
    dut.uio_in.value = 0
    dut.ui_in.value = 0
    dut.ena.value = 1

    await Timer(100, unit="ns")
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)


async def boot_cpu(dut):
    dut._log.info("Booting CPU ")

    cocotb.start_soon(Clock(dut.clk, 40, unit="ns").start())
    pins = TTPins(dut)
    flash = QspiFlash(dut, pins, verbose=True, log_bytes=True)
    ram = SpiRam(dut, pins)
    return pins, flash, ram


from test_tiny_instructions import *


#@cocotb.test()
async def test_cpu_fibonacci_compiler(dut):
    dut._log.info("Starting CPU test")
    pins, flash, ram = await boot_cpu(dut)

    # preload first
    dut._log.info("Loaded Fibonacci program into flash")
    program_path = Path(__file__).with_name("fibonacci.bin")
    if program_path.exists():
        flash.load_file(program_path, base_addr=0x0000)

    ram.poke16(0x0010, 0x1234)
    ram.poke16(0x0012, 0xABCD)
    flash.poke16(0x0100, 0xBEEF)

    # start peripherals BEFORE reset release
    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())

    await reset_dut(dut)
    await Timer(605, unit="us")
    cocotb.log.info("uo_out is %d", (dut.uo_out.value))
    await Timer(1745, unit="us")

    cocotb.log.info("uo_out is %d", (dut.uo_out.value))
    await Timer(2800, unit="us")

    cocotb.log.info("uo_out is %d", (dut.uo_out.value))
    await Timer(3400, unit="us")

    cocotb.log.info("uo_out is %d", (dut.uo_out.value))
    await Timer(6400, unit="us")

    cocotb.log.info("uo_out is %d", (dut.uo_out.value))
