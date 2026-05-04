import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer, ClockCycles

from common import TTPins
from spimemory import SpiMemoryDevice, SpiRam, TTContinuousQSPIFlash


CLOCK_PERIOD_NS = 40
RESET_HOLD_NS = 100
RESET_SETTLE_CYCLES = 10


async def reset_dut(dut):
    dut._log.info("Resetting DUT")
    dut._qspi_test_resynced = False
    dut.rst_n.value = 0
    dut.uio_in.value = 0
    dut.ui_in.value = 0
    dut.ena.value = 1

    await Timer(RESET_HOLD_NS, unit="ns")
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, RESET_SETTLE_CYCLES)


async def boot_cpu(dut) -> tuple[TTPins, SpiMemoryDevice, SpiMemoryDevice]:
    """Start the clock and create external memory models.

    The flash model keeps word_write_offset_bytes=2 by default because your
    current simulation flow starts runtime flash fetches from byte 0x000002.
    When the init/start resync is fully fixed, change this to 0 here.
    """
    dut._log.info("Booting CPU")
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD_NS, unit="ns").start())

    pins = TTPins(dut)
    flash = TTContinuousQSPIFlash(dut, pins, word_write_offset_bytes=2)
    ram = SpiRam(dut, pins, verbose=False)

    return pins, flash, ram


def load_program(flash, words, start_word: int = 0):
    """Convenience loader for dense word programs."""
    flash.load_words_w(start_word, words)


def load_program_map(flash, word_map: dict[int, int]):
    """Convenience loader for sparse programs/data tables."""
    flash.load_word_map(word_map)


async def start_memories_and_reset(dut, flash, ram):
    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())
    await reset_dut(dut)
