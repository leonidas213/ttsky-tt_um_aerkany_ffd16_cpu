"""
Gate-level friendly Remedy CPU batch test.

This test cold-boots the DUT only once, lets the QSPI/flash init happen once,
then reuses the debugger to halt, patch the flash model, jump PC to 0, and run
many small programs.

It intentionally does NOT wait on internal signals such as execute_now_pulse.
Instruction progress is counted from the external flash model only.
"""

import cocotb
from cocotb.triggers import RisingEdge, Timer, with_timeout

from common import wait_execute_steps, is_gate_level
from tb_setup import boot_cpu, reset_dut


# Debugger pin overlap masks.
#   ui_in[7]  = debug clock, ui_in[6] = debug data input
#   uo_out[7] = debug response output
# So normal CPU program checks must ignore uo_out[7], and normal CPU input
# values should not intentionally use ui_in[6:7] while this test uses debugger.
DEBUG_UI_MASK = 0xC0
USER_UI_MASK = 0x3F
DEBUG_UO_MASK = 0x80
CPU_UO_CHECK_MASK = 0x7F


# -----------------------------------------------------------------------------
# Tiny serial debugger protocol
# -----------------------------------------------------------------------------


class DebugSerialTiny:
    """Python bit-bang driver for debug_serial_frontend_tiny.

    DUT pin mapping from the top module:
      ui_in[7]  -> dbg_clk
      ui_in[6]  -> dbg_data_in
      uo_out[7] -> dbg_data_out when the frontend drives a response

    Protocol:
      MSB first, 32 command clocks:
        8'hA5 sync + 4-bit cmd + 4-bit addr + 16-bit data
      Then 16 response bits, MSB first.
    """

    CMD_PING = 0x0
    CMD_READ = 0x1
    CMD_WRITE = 0x2

    REG_ID = 0x0
    REG_STATUS = 0x1
    REG_CONTROL = 0x2
    REG_FLAGS = 0x3
    REG_PC = 0x4
    REG_IR = 0x5
    REG_JUMP_ADDR = 0x8

    # STATUS layout used by both full and debug-lite core:
    STATUS_HALT_REQ = 1 << 0
    STATUS_JUMP_PENDING = 1 << 1
    STATUS_HALTED = 1 << 3
    STATUS_DBG_ENABLE = 1 << 4

    def __init__(self, dut, phase_cycles=10):
        self.dut = dut
        self.phase_cycles = int(phase_cycles)
        self.ui_shadow = self._safe_int(dut.ui_in.value) & 0xFF
        # Idle debug clock low. Keep debug data low so InputReg bit6 is not
        # accidentally read as 1 after a debug transaction.
        self.set_dbg_pins(data=0, clk=0)

    @staticmethod
    def _safe_int(value):
        try:
            return int(value)
        except Exception:
            return 0

    async def cycles(self, n=None):
        n = self.phase_cycles if n is None else int(n)
        for _ in range(max(1, n)):
            await RisingEdge(self.dut.clk)

    def set_ui(self, value):
        self.ui_shadow = int(value) & 0xFF
        self.dut.ui_in.value = self.ui_shadow

    def set_user_input(self, value):
        """Set ui_in for CPU input tests, excluding debugger pins.

        ui_in[6] and ui_in[7] are owned by the debugger serial interface in this
        test. Keep them low after transactions so CPU input tests only use
        ui_in[5:0].
        """
        value = int(value) & USER_UI_MASK
        self.set_ui(value)

    def set_dbg_pins(self, data=None, clk=None):
        if data is not None:
            if data:
                self.ui_shadow |= 1 << 6
            else:
                self.ui_shadow &= ~(1 << 6)
        if clk is not None:
            if clk:
                self.ui_shadow |= 1 << 7
            else:
                self.ui_shadow &= ~(1 << 7)
        self.dut.ui_in.value = self.ui_shadow

    def response_bit(self):
        s = str(self.dut.uo_out.value).strip()
        if not s or len(s) < 8:
            return 0
        return 1 if s[-1 - 7] == "1" else 0

    async def _send_bit(self, bit):
        self.set_dbg_pins(data=bit, clk=0)
        await self.cycles()
        self.set_dbg_pins(clk=1)
        await self.cycles()
        # Keep the high phase long enough for the synchronized frontend to move
        # through S_EXEC/S_LOAD_TX/S_TURNAROUND on the last command bit.
        self.set_dbg_pins(clk=0)
        await self.cycles()

    async def xfer(self, cmd, addr=0, data=0, read_response=True):
        word = (0xA5 << 24) | ((cmd & 0xF) << 20) | ((addr & 0xF) << 16) | (data & 0xFFFF)

        self.set_dbg_pins(data=0, clk=0)
        await self.cycles(2 * self.phase_cycles)

        for bit_index in range(31, -1, -1):
            await self._send_bit((word >> bit_index) & 1)

        # IMPORTANT:
        # The frontend always enters a 16-bit response phase after every valid
        # command, including writes. If we stop here, the frontend stays stuck in
        # S_TURNAROUND/S_TX and the next command becomes desynchronized.
        #
        # So for write-only commands we still CLOCK/DRAIN the 16 response bits,
        # but we ignore the returned value unless read_response=True.
        self.set_dbg_pins(data=0, clk=0)
        await self.cycles(2 * self.phase_cycles)

        resp = 0
        for _ in range(16):
            self.set_dbg_pins(clk=1)
            await self.cycles()
            resp = ((resp << 1) | self.response_bit()) & 0xFFFF
            self.set_dbg_pins(clk=0)
            await self.cycles()

        # Park debug pins low after the response drain. This matters because
        # ui_in[6:7] are also normal CPU input pins.
        self.set_dbg_pins(data=0, clk=0)
        await self.cycles(2 * self.phase_cycles)

        if not read_response:
            return None
        return resp

    async def ping(self):
        return await self.xfer(self.CMD_PING, 0, 0, read_response=True)

    async def read(self, addr):
        return await self.xfer(self.CMD_READ, addr, 0, read_response=True)

    async def write(self, addr, data, read_ack=False):
        # Writes still drain the mandatory 16 response clocks to return the
        # frontend to idle, but by default the caller ignores the response value.
        resp = await self.xfer(self.CMD_WRITE, addr, data, read_response=True)
        if read_ack and resp != 0xACCE:
            self.dut._log.warning("debug write addr=0x%X data=0x%04X returned 0x%04X, expected 0xACCE", addr, data, resp)
        return resp if read_ack else None

    async def enable(self):
        await self.write(self.REG_CONTROL, 0x0001)

    async def halt(self):
        await self.write(self.REG_CONTROL, 0x0003)  # enable + halt request

    async def run(self):
        await self.write(self.REG_CONTROL, 0x0005)  # enable + run pulse

    async def step(self):
        await self.write(self.REG_CONTROL, 0x0009)  # enable + step pulse

    async def jump(self, addr):
        await self.write(self.REG_JUMP_ADDR, addr & 0xFFFF)
        await self.write(self.REG_CONTROL, 0x0041)  # enable + jump/load-PC request

    async def wait_status(self, mask, value, timeout_ns=None, poll_gap_ns=20_000):
        if timeout_ns is None:
            timeout_ns = 250_000_000 if is_gate_level() else 5_000_000

        async def _wait():
            while True:
                status = await self.read(self.REG_STATUS)
                if (status & mask) == value:
                    return status
                await Timer(poll_gap_ns, units="ns")

        return await with_timeout(_wait(), timeout_ns, "ns")

    async def wait_halted(self, timeout_ns=None):
        return await self.wait_status(self.STATUS_HALTED, self.STATUS_HALTED, timeout_ns=timeout_ns)

    async def wait_running(self, timeout_ns=None):
        return await self.wait_status(self.STATUS_HALTED, 0, timeout_ns=timeout_ns)


# -----------------------------------------------------------------------------
# Batch helpers
# -----------------------------------------------------------------------------


def clear_flash_trace(flash):
    """Reset only testbench fetch counters/events, not the memory contents."""
    from cocotb.triggers import Event

    flash.fetch_word_count = 0
    flash.instr_count = 0
    flash.literal_count = 0
    flash.last_fetch_byte_addr = None
    flash.last_fetch_word_addr = None
    flash.last_fetch_word = None
    flash._word_event = Event()
    flash._instr_event = Event()


def load_program(flash, words, clear_words=0x0400):
    """Patch the simulated flash while CPU is halted.

    words may be either:
      - list/tuple: loaded from word address 0
      - dict: {word_addr: word}
    """
    for i in range(clear_words):
        flash.poke16w(i, 0x0000)

    if isinstance(words, dict):
        for addr, word in words.items():
            flash.poke16w(addr, word)
    else:
        for addr, word in enumerate(words):
            flash.poke16w(addr, word)


def clear_ram(ram):
    if hasattr(ram, "mem"):
        ram.mem[:] = bytes([0x00]) * len(ram.mem)


async def wait_external_memory_idle(dut, pins, stable_cycles=24, timeout_ns=10_000_000):
    async def _wait():
        stable = 0
        while stable < stable_cycles:
            await RisingEdge(dut.clk)
            if pins.flash_cs == 1 and pins.ram_cs == 1:
                stable += 1
            else:
                stable = 0

    await with_timeout(_wait(), timeout_ns, "ns")


async def run_program_case(dut, dbg, pins, flash, ram, case):
    name = case["name"]
    dut._log.info("===== DEBUG BATCH CASE: %s =====", name)

    await dbg.halt()
    await dbg.wait_halted()
    await wait_external_memory_idle(dut, pins)

    if case.get("clear_ram", True):
        clear_ram(ram)

    load_program(flash, case["words"], clear_words=case.get("clear_words", 0x0400))
    clear_flash_trace(flash)

    # Debug command transactions use ui_in[6:7], so set the requested CPU input
    # before jump/run and again immediately after the run response is drained.
    # This keeps input-register tests from accidentally reading debugger bits.
    user_input = case.get("ui_in", 0x00) & USER_UI_MASK
    dbg.set_user_input(user_input)

    await dbg.jump(case.get("start_pc", 0x0000))
    dbg.set_user_input(user_input)
    await dbg.run()
    dbg.set_user_input(user_input)

    if "checks" in case:
        for step_count, expected in case["checks"]:
            await wait_execute_steps(dut, step_count, flash, timeout_ns=case.get("timeout_ns"))
            raw = int(dut.uo_out.value) & 0xFF
            got = raw & CPU_UO_CHECK_MASK
            exp = expected & CPU_UO_CHECK_MASK
            assert got == exp, (
                f"{name}: expected masked 0x{exp:02X}, got masked 0x{got:02X} "
                f"raw_uo=0x{raw:02X} mask=0x{CPU_UO_CHECK_MASK:02X}"
            )
    else:
        await wait_execute_steps(dut, case["steps"], flash, timeout_ns=case.get("timeout_ns"))
        raw = int(dut.uo_out.value) & 0xFF
        got = raw & CPU_UO_CHECK_MASK

        if case.get("kind") == "nonzero":
            assert got != 0, (
                f"{name}: expected masked non-zero output, got masked 0x{got:02X} "
                f"raw_uo=0x{raw:02X} mask=0x{CPU_UO_CHECK_MASK:02X}"
            )
        else:
            expected = case["expected"] & CPU_UO_CHECK_MASK
            assert got == expected, (
                f"{name}: expected masked 0x{expected:02X}, got masked 0x{got:02X} "
                f"raw_uo=0x{raw:02X} mask=0x{CPU_UO_CHECK_MASK:02X}"
            )

    await dbg.halt()
    await dbg.wait_halted()
    await wait_external_memory_idle(dut, pins)


# -----------------------------------------------------------------------------
# Programs
# -----------------------------------------------------------------------------

# Converted from the original standalone test files.
# This is intentionally one cocotb test so QSPI init/cold reset happens once.
CASES = [
    {
        'name': 'test_alu__add_val',
        'words': [0x3D02, 0x0000, 0x4400, 0x0A05, 0x0A12, 0x0201, 0x3F10, 0x3DFF],
        'steps': 9,
        'expected': 0x07,
    },
    {
        'name': 'test_alu__mov_reg',
        'words': [0x3D02, 0x0000, 0x4400, 0x0A19, 0x0101, 0x3F10, 0x3DFF],
        'steps': 6,
        'expected': 0x09,
    },
    {
        'name': 'test_alu__add_reg',
        'words': [0x3D02, 0x0000, 0x4400, 0x0A05, 0x0A12, 0x0201, 0x3F10, 0x3DFF],
        'steps': 7,
        'expected': 0x07,
    },
    {
        'name': 'test_alu__add_imm4',
        'words': [0x3D02, 0x0000, 0x4400, 0x0A05, 0x0C03, 0x3F10, 0x3DFF],
        'steps': 6,
        'expected': 0x08,
    },
    {
        'name': 'test_alu__sub_reg',
        'words': [0x3D02, 0x0000, 0x4400, 0x0A09, 0x0A12, 0x0401, 0x3F10, 0x3DFF],
        'steps': 7,
        'expected': 0x07,
    },
    {
        'name': 'test_alu__and_reg',
        'words': [0x3D02, 0x0000, 0x4400, 0x0A0E, 0x0A1B, 0x0601, 0x3F10, 0x3DFF],
        'steps': 7,
        'expected': 0x0A,
    },
    {
        'name': 'test_alu__or_reg',
        'words': [0x3D02, 0x0000, 0x4400, 0x0A0A, 0x0A15, 0x0701, 0x3F10, 0x3DFF],
        'steps': 7,
        'expected': 0x0F,
    },
    {
        'name': 'test_alu__xor_reg',
        'words': [0x3D02, 0x0000, 0x4400, 0x0A0F, 0x0A1A, 0x0801, 0x3F10, 0x3DFF],
        'steps': 7,
        'expected': 0x05,
    },
    {
        'name': 'test_alu__neg',
        'words': [0x3D02, 0x0000, 0x4400, 0x0A01, 0x1300, 0x3F10, 0x3DFF],
        'steps': 6,
        'expected': 0xFF,
    },
    {
        'name': 'test_alu__not',
        'words': [0x3D02, 0x0000, 0x4400, 0x0A00, 0x1A00, 0x3F10, 0x3DFF],
        'steps': 6,
        'expected': 0xFF,
    },
    {
        'name': 'test_alu__lsl',
        'words': [0x3D02, 0x0000, 0x4400, 0x0A03, 0x2400, 0x3F10, 0x3DFF],
        'steps': 6,
        'expected': 0x06,
    },
    {
        'name': 'test_alu__lsr',
        'words': [0x3D02, 0x0000, 0x4400, 0x0A08, 0x2500, 0x3F10, 0x3DFF],
        'steps': 6,
        'expected': 0x04,
    },
    {
        'name': 'test_alu__asr',
        'words': [0x3D02, 0x0000, 0x4400, 0xFFFE, 0x0901, 0x2800, 0x3F10, 0x3DFF],
        'steps': 8,
        'expected': 0xFF,
    },
    {
        'name': 'test_alu__swap',
        'words': [0x3D02, 0x0000, 0x4400, 0x9234, 0x0900, 0x2900, 0x3F10, 0x3DFF],
        'steps': 9,
        'expected': 0x12,
    },
    {
        'name': 'test_alu__swapn',
        'words': [0x3D02, 0x0000, 0x4400, 0x9234, 0x0900, 0x2A00, 0x3F10, 0x3DFF],
        'steps': 9,
        'expected': 0x43,
    },
    {
        'name': 'test_alu__adc_no_carry_in',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x0A05, 0x0A12, 0x1E00, 0x0301, 0x3F10,
        0x3DFF,
    ],
        'steps': 10,
        'expected': 0x07,
    },
    {
        'name': 'test_alu__adc_with_carry_in',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x0A20, 0x1021, 0x0A05, 0x0A12, 0x0301,
        0x3F10, 0x3DFF,
    ],
        'steps': 9,
        'expected': 0x08,
    },
    {
        'name': 'test_alu__sbc_with_borrow',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x0A20, 0x1021, 0x0A09, 0x0A12, 0x0501,
        0x3F10, 0x3DFF,
    ],
        'steps': 9,
        'expected': 0x06,
    },
    {
        'name': 'test_alu__lsl_sets_carry',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x8000, 0x0901, 0x2400, 0x8003, 0x3400,
        0x0A11, 0x3F11, 0x3D02, 0x0A15, 0x3F11, 0x3DFF,
    ],
        'steps': 12,
        'expected': 0x05,
    },
    {
        'name': 'test_alu__lsr_sets_carry',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x0A01, 0x2500, 0x8003, 0x3400, 0x0A11,
        0x3F11, 0x3D02, 0x0A14, 0x3F11, 0x3DFF,
    ],
        'steps': 9,
        'expected': 0x04,
    },
    {
        'name': 'test_alu__rol_uses_carry',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x0A20, 0x1021, 0x0A00, 0x2600, 0x3F10,
        0x3DFF,
    ],
        'steps': 8,
        'expected': 0x01,
    },
    {
        'name': 'test_alu__ror_uses_carry',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x0A20, 0x1021, 0x0A00, 0x2700, 0x8003,
        0x3600, 0x0A11, 0x3F11, 0x3D02, 0x0A13, 0x3F11, 0x3DFF,
    ],
        'steps': 14,
        'expected': 0x03,
    },
    {
        'name': 'test_alu__ldi_i16_positive',
        'words': [0x3D02, 0x0000, 0x4400, 0x9234, 0x0900, 0x3F10, 0x3DFF],
        'steps': 6,
        'expected': 0x34,
    },
    {
        'name': 'test_alu__add_i16_negative',
        'words': [0x3D02, 0x0000, 0x4400, 0x0A05, 0xFFFE, 0x0B01, 0x3F10, 0x3DFF],
        'steps': 9,
        'expected': 0x03,
    },
    {
        'name': 'test_branch__cmp_jumpzero',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x0A05, 0x0A15, 0x1E01, 0x8003, 0x3500,
        0x0A21, 0x3F12, 0x3D02, 0x0A29, 0x3F12, 0x3DFF,
    ],
        'steps': 10,
        'expected': 0x09,
    },
    {
        'name': 'test_branch__cmp_jumpnotzero',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x0A05, 0x0A14, 0x1E01, 0x8003, 0x3800,
        0x0A21, 0x3F12, 0x3D02, 0x0A28, 0x3F12, 0x3DFF,
    ],
        'steps': 10,
        'expected': 0x08,
    },
    {
        'name': 'test_branch__jump_abs',
        'words': {
        0x0000: 0x80FF,
        0x0001: 0x3C00,
        0x00FF: 0x0A0C,
        0x0100: 0x3F10,
        0x0101: 0x82FF,
        0x0102: 0x3C00,
        0x02FF: 0x8101,
        0x0300: 0x3C00,
    },
        'steps': 9,
        'expected': 0x0C,
    },
    {
        'name': 'test_branch__jumpzero_taken',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x0A05, 0x2105, 0x8003, 0x3500, 0x0A11,
        0x3F11, 0x3D02, 0x0A19, 0x3F11, 0x3DFF,
    ],
        'steps': 12,
        'expected': 0x09,
    },
    {
        'name': 'test_branch__jumpnotzero_taken',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x0A05, 0x2104, 0x8003, 0x3800, 0x0A11,
        0x3F11, 0x3D02, 0x0A18, 0x3F11, 0x3DFF,
    ],
        'steps': 10,
        'expected': 0x08,
    },
    {
        'name': 'test_branch__jumpnegative_taken',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x0A01, 0x2102, 0x8003, 0x3600, 0x0A11,
        0x3F11, 0x3D02, 0x0A17, 0x3F11, 0x3DFF,
    ],
        'steps': 10,
        'expected': 0x07,
    },
    {
        'name': 'test_branch__jumpcarry_taken',
        'words': [
        0x3D02, 0x0000, 0x4400, 0xFFFF, 0x0901, 0x0C01, 0x8003, 0x3400,
        0x0A11, 0x3F11, 0x3D02, 0x0A16, 0x3F11, 0x3DFF,
    ],
        'steps': 10,
        'expected': 0x06,
    },
    {
        'name': 'test_branch__countdown_loop',
        'words': [0x3D02, 0x0000, 0x4400, 0x0A05, 0x1001, 0xfffd, 0x3801, 0x3F10, 0x3DFF],
        'steps': 20,
        'expected': 0x00,
    },
    {
        'name': 'test_memory__st_ld_absolute',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x8034, 0x0900, 0x8010, 0x2D00, 0x8010,
        0x2F10, 0x3F11, 0x3DFF,
    ],
        'steps': 10,
        'expected': 0x34,
    },
    {
        'name': 'test_memory__st_ld_ptr',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x8012, 0x0920, 0x8056, 0x0900, 0x2B20,
        0x2C12, 0x3F11, 0x3DFF,
    ],
        'steps': 12,
        'expected': 0x56,
    },
    {
        'name': 'test_memory__st_ld_offset',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x8020, 0x0920, 0x8077, 0x0900, 0x8003,
        0x3120, 0x8003, 0x3212, 0x3F11, 0x3DFF,
    ],
        'steps': 12,
        'expected': 0x77,
    },
    {
        'name': 'test_memory__mem_addr_zero',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x8044, 0x0900, 0x2E00, 0x3010, 0x3F11,
        0x3DFF,
    ],
        'steps': 12,
        'expected': 0x44,
    },
    {
        'name': 'test_memory__mem_high_addr',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x8066, 0x0900, 0xFFFF, 0x2D10, 0xFFFF,
        0x2F11, 0x3F11, 0x3DFF,
    ],
        'steps': 12,
        'expected': 0x66,
    },
    {
        'name': 'test_memory__flash_read',
        'words': {
        0x0000: 0x8002,
        0x0001: 0x3700,
        0x0002: 0x0000,
        0x0003: 0x4400,
        0x0004: 0x8100,
        0x0005: 0x0910,
        0x0006: 0x4501,
        0x0007: 0x3F10,
        0x0008: 0x0C11,
        0x0009: 0xFFFB,
        0x000A: 0x3901,
        0x00FF: 0x002F,
        0x0100: 0x002F,
        0x0101: 0x002F,
        0x0102: 0x002F,
        0x0103: 0x002F,
    },
        'steps': 14,
        'expected': 0x2F,
    },
    {
        'name': 'test_stack_call__rcall_rret',
        'words': [
        0x3D04, 0x0000, 0x4400, 0x0A0B, 0x3B0F, 0x8004, 0x3AF0, 0x3F10,
        0x3DFF,
    ],
        'steps': 14,
        'expected': 0x0B,
    },
    {
        'name': 'test_stack_call__push_pop_basic',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x8100, 0x09E0, 0x8034, 0x0900, 0x10E1,
        0x2BE0, 0x0A00, 0x2C1E, 0x0CE1, 0x3F11, 0x3DFF,
    ],
        'steps': 15,
        'expected': 0x34,
    },
    {
        'name': 'test_stack_call__push_pop_lifo',
        'words': [
        0x3D02, 0x0000, 0x4400, 0xFFFF, 0x09E1, 0x8011, 0x0900, 0x8022,
        0x0910, 0x8010, 0x0920, 0x10E1, 0x2BE0, 0x10E1, 0x2BE1, 0x2C2E,
        0x0CE1, 0x2C3E, 0x0CE1, 0x3F12, 0x8014, 0x3C00,
    ],
        'steps': 25,
        'expected': 0x22,
    },
    {
        'name': 'test_stack_call__push_pop_lifo_second_value',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x8100, 0x09E0, 0x8011, 0x0900, 0x8022,
        0x0910, 0x10E1, 0x2BE0, 0x10E1, 0x2BE1, 0x2C2E, 0x0CE1, 0x2C3E,
        0x0CE1, 0x3F13, 0x8012, 0x3C00,
    ],
        'steps': 25,
        'expected': 0x11,
    },
    {
        'name': 'test_stack_call__rcall_rret_basic',
        'words': [
        0x3D05, 0x0000, 0x4400, 0x8055, 0x0900, 0x3B0F, 0x8004, 0x3AF0,
        0x3F10, 0x3DFF,
    ],
        'steps': 14,
        'expected': 0x55,
    },
    {
        'name': 'test_stack_call__call_macro_basic',
        'words': [
        0x3D07, 0x0000, 0x4400, 0x8066, 0x0900, 0x2CFE, 0x0CE1, 0x3B0F,
        0x8100, 0x09E0, 0x10E1, 0x8011, 0x09F0, 0x2BEF, 0x8004, 0x3C00,
        0x3F10, 0x3DFF,
    ],
        'steps': 17,
        'expected': 0x66,
    },
    {
        'name': 'test_stack_call__enter_leave_basic',
        'words': [
        0x3D0E, 0x0000, 0x4400, 0x10E1, 0x2BED, 0x01DE, 0x10E2, 0x8021,
        0x0900, 0x01ED, 0x2CDE, 0x0CE1, 0x2CFE, 0x0CE1, 0x3B0F, 0x8100,
        0x09E0, 0x10E1, 0x8018, 0x09F0, 0x2BEF, 0x8004, 0x3C00, 0x3F10,
        0x3DFF,
    ],
        'steps': 25,
        'expected': 0x21,
    },
    {
        'name': 'test_stack_call__bp_local_access_style',
        'words': [
        0x3D13, 0x0000, 0x4400, 0x10E1, 0x2BED, 0x01DE, 0x10E2, 0x805A,
        0x0900, 0xFFFF, 0x31D0, 0xFFFF, 0x321D, 0x0CE1, 0x3F11, 0x01ED,
        0x2CDE, 0x0CE1, 0x2CFE, 0x0CE1, 0x3B0F, 0x8100, 0x09E0, 0x10E1,
        0x801D, 0x09F0, 0x2BEF, 0x8004, 0x3C00, 0x3F10, 0x3DFF,
    ],
        'steps': 36,
        'expected': 0x5A,
    },
    {
        'name': 'test_stack_call__scall_macro',
        'words': [
        0x3D05, 0x0000, 0x4400, 0x802B, 0x0900, 0x3B0F, 0x8100, 0x09E0,
        0x10E1, 0x2BEF, 0x8004, 0x3AF0, 0x2CFE, 0x0CE1, 0x3F10, 0x3DFF,
    ],
        'steps': 20,
        'expected': 0x2B,
    },
    {
        'name': 'test_stack_call__push_writes_stack_memory',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x8100, 0x09E0, 0x804D, 0x0900, 0x10E1,
        0x2BE0, 0x3F10, 0x3DFF,
    ],
        'steps': 12,
        'expected': 0x4D,
    },
    {
        'name': 'test_io_interrupt__in_inputreg',
        'words': [0x3D02, 0x0000, 0x4400, 0x4200, 0x3F10, 0x3DFF],
        'ui_in': 0x25,
        'steps': 6,
        'expected': 0x25,
    },
    {
        'name': 'test_io_interrupt__rng_seed_and_read',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x9234, 0x09C0, 0x3FBC, 0x420C, 0x3F10,
        0x3DFF,
    ],
        'steps': 10,
        'kind': 'nonzero',
    },
    {
        'name': 'test_io_interrupt__rng_changes',
        'words': [
        0x3D02, 0x0000, 0x4400, 0x9234, 0x09C0, 0x3FBC, 0x420C, 0x421C,
        0x0801, 0x3F10, 0x3DFF,
    ],
        'steps': 13,
        'kind': 'nonzero',
    },
    {
        'name': 'test_io_interrupt__timer1_interrupt_basic',
        'words': [
        0x3D0D, 0x0000, 0x8077, 0x0900, 0x3F10, 0x803F, 0x0920, 0x425D,
        0x425E, 0x425F, 0x3FF2, 0x0A21, 0x3F42, 0x4400, 0x0A21, 0x3FD2,
        0x0A21, 0x3FE2, 0x801F, 0x0920, 0x3F32, 0x8041, 0x0920, 0x3F22,
        0x3DFF,
    ],
        'steps': 60,
        'expected': 0x77,
        'timeout_ns': 500000000,
        'group': 'interrupt_last',
    },
]

@cocotb.test()
async def test_debugger_full_suite_without_cold_reset(dut):
    """Cold boot once, then run many programs through debugger halt/jump/run."""

    pins, flash, ram = await boot_cpu(dut)
    flash.trace_fetch = True

    # Safe initial program while QSPI init is happening. The debugger will halt
    # the CPU before the real batch programs are patched in.
    load_program(flash, [0x3DFF], clear_words=0x0400)

    cocotb.start_soon(flash.run())
    cocotb.start_soon(ram.run())

    await reset_dut(dut)

    dbg = DebugSerialTiny(dut, phase_cycles=12 if is_gate_level() else 8)

    ping = await dbg.ping()
    dut._log.info("debug ping response = 0x%04X", ping)
    assert ping == 0xDB12, f"debug ping failed: got 0x{ping:04X}"

    dbg_id = await dbg.read(DebugSerialTiny.REG_ID)
    dut._log.info("debug core ID = 0x%04X", dbg_id)
    assert dbg_id in (0xDB11, 0xDB21), f"unexpected debug core ID: 0x{dbg_id:04X}"

    # Request halt immediately after reset. On gate-level sim this may only
    # become true after the real QSPI init delay and first CPU fetch.
    await dbg.halt()
    await dbg.wait_halted(timeout_ns=300_000_000 if is_gate_level() else 10_000_000)
    await wait_external_memory_idle(dut, pins)

    for case in CASES:
        await run_program_case(dut, dbg, pins, flash, ram, case)

    dut._log.info("All debugger batch cases passed without another cold reset")
