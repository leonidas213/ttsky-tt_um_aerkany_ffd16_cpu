
from cocotb.triggers import RisingEdge, ReadWrite, ReadOnly, with_timeout
from cocotb.handle import Force, Release

class TTPins:
    """Tiny Tapeout uio pin helper.

    The DUT exposes all external-memory pins through uio_out/uio_in.  These
    helpers keep the bit mapping in one place and avoid duplicating string-based
    bit extraction across the memory models.
    """

    SPI_FLASH_CS = 0
    SPI_MOSI = 1
    SPI_MISO = 2
    SPI_SCLK = 3
    SPI_RAM_CS = 6

    # Shared QSPI pins
    QSPI_IO0 = 1
    QSPI_IO1 = 2
    QSPI_IO2 = 4
    QSPI_IO3 = 5

    def __init__(self, dut):
        self.dut = dut
        self._uio_in_shadow = 0
        self.dut.uio_in.value = 0

    def out_bit(self, idx: int) -> int:
        """Read one uio_out bit safely, treating X/Z as 0."""
        s = str(self.dut.uio_out.value).strip()
        if not s or len(s) <= idx:
            return 0
        ch = s[-1 - idx]
        if ch == "1":
            return 1
        if ch == "0":
            return 0
        return 0

    def set_in_bit(self, idx: int, value: int):
        """Drive one uio_in bit using a shadow register."""
        if value:
            self._uio_in_shadow |= 1 << idx
        else:
            self._uio_in_shadow &= ~(1 << idx)
        self.dut.uio_in.value = self._uio_in_shadow

    @property
    def flash_cs(self) -> int:
        return self.out_bit(self.SPI_FLASH_CS)

    @property
    def ram_cs(self) -> int:
        return self.out_bit(self.SPI_RAM_CS)

    @property
    def sclk(self) -> int:
        return self.out_bit(self.SPI_SCLK)

    @property
    def mosi(self) -> int:
        return self.out_bit(self.SPI_MOSI)

    @property
    def qspi_out_nibble(self) -> int:
        return (
            (self.out_bit(self.QSPI_IO0) << 0)
            | (self.out_bit(self.QSPI_IO1) << 1)
            | (self.out_bit(self.QSPI_IO2) << 2)
            | (self.out_bit(self.QSPI_IO3) << 3)
        )

    def drive_miso(self, bit: int):
        self.set_in_bit(self.SPI_MISO, bit)

    def drive_qspi_nibble(self, value: int):
        value &= 0xF
        self.set_in_bit(self.QSPI_IO0, (value >> 0) & 1)
        self.set_in_bit(self.QSPI_IO1, (value >> 1) & 1)
        self.set_in_bit(self.QSPI_IO2, (value >> 2) & 1)
        self.set_in_bit(self.QSPI_IO3, (value >> 3) & 1)

    def release_qspi(self):
        # uio_in cannot be Z in this testbench, so idle is driven as 0.
        self.set_in_bit(self.QSPI_IO0, 0)
        self.set_in_bit(self.QSPI_IO1, 0)
        self.set_in_bit(self.QSPI_IO2, 0)
        self.set_in_bit(self.QSPI_IO3, 0)


# -----------------------------------------------------------------------------
# HDL handle helpers
# -----------------------------------------------------------------------------


def _id(parent, name: str):
    try:
        return getattr(parent, name)
    except Exception:
        return parent._id(name, extended=False)


def hdl_path(dut, path: str):
    h = dut
    for part in path.split("."):
        h = _id(h, part)
    return h


def find_handle(root, name: str):
    """Recursive fallback search. Prefer hdl_path for duplicated names."""
    try:
        return getattr(root, name)
    except Exception:
        pass

    try:
        return root._id(name, extended=False)
    except Exception:
        pass

    try:
        children = list(root)
    except Exception:
        children = []

    for child in children:
        try:
            return find_handle(child, name)
        except LookupError:
            pass

    raise LookupError(f"Could not find HDL handle named {name}")


def find_first_handle(root, names):
    last = None
    for name in names:
        try:
            return find_handle(root, name)
        except LookupError as e:
            last = e
    raise last if last is not None else LookupError("No handle names given")


def find_first_path(root, paths, fallback_names=()):
    """Try exact HDL paths first, then recursive leaf names."""
    last = None
    for path in paths:
        try:
            return hdl_path(root, path)
        except Exception as e:
            last = e

    if fallback_names:
        try:
            return find_first_handle(root, fallback_names)
        except Exception as e:
            last = e

    raise LookupError(str(last) if last else "No HDL paths given")


# -----------------------------------------------------------------------------
# Optional simulation-only init helpers
# -----------------------------------------------------------------------------


async def clamp_qspi_init_waits(dut):
    """Simulation-only helper that shortens the QSPI init wait counter.

    Prefer compile-time fast-init parameters if possible.  This helper remains
    here because it is useful when you cannot touch/elaborate the Verilog params.
    """
    init_wait_cnt = find_first_path(
        dut,
        (
            "tt_um_remedy_cpu.qspi_memory_interface_i19.init_wait_cnt",
            "qspi_memory_interface_i19.init_wait_cnt",
        ),
        ("init_wait_cnt",),
    )
    init_done = find_first_path(
        dut,
        (
            "tt_um_remedy_cpu.qspi_memory_interface_i19.init_done_r",
            "qspi_memory_interface_i19.init_done_r",
        ),
        ("init_done_r", "init_done"),
    )

    while True:
        await RisingEdge(dut.clk)
        await ReadWrite()

        if str(dut.rst_n.value) != "1":
            try:
                init_wait_cnt.value = Release()
            except Exception:
                pass
            continue

        try:
            if int(init_done.value) == 1:
                init_wait_cnt.value = Release()
                dut._log.info("QSPI init wait clamp released")
                return
        except Exception:
            pass

        init_wait_cnt.value = Force(0)


async def _resync_cpu_after_qspi_init(dut):
    """Best-effort simulation resync after QSPI init.

    If the exact internal handles are not present, this function logs a warning
    and returns.  The flash model also has a word-address offset option, so your
    tests can still run even when the hierarchy is flattened differently.
    """
    if getattr(dut, "_qspi_test_resynced", False):
        return

    try:
        init_done = find_first_path(
            dut,
            (
                "tt_um_remedy_cpu.qspi_memory_interface_i19.init_done_r",
                "qspi_memory_interface_i19.init_done_r",
            ),
            ("init_done_r", "init_done"),
        )
        cpu_state = find_first_path(
            dut,
            (
                "tt_um_remedy_cpu.cpu_cycle_controller_tiny_i16.state",
                "cpu_cycle_controller_tiny_i16.state",
            ),
        )
        mem_state = find_first_path(
            dut,
            (
                "tt_um_remedy_cpu.memory_wait_controller_tiny_i17.state",
                "memory_wait_controller_tiny_i17.state",
            ),
        )
        mem_op = find_first_path(
            dut,
            (
                "tt_um_remedy_cpu.memory_wait_controller_tiny_i17.op",
                "memory_wait_controller_tiny_i17.op",
            ),
        )
        mem_stall = find_first_path(
            dut,
            (
                "tt_um_remedy_cpu.memory_wait_controller_tiny_i17.mem_stall",
                "memory_wait_controller_tiny_i17.mem_stall",
            ),
        )
        fetch_done = find_first_path(
            dut,
            (
                "tt_um_remedy_cpu.memory_wait_controller_tiny_i17.fetch_done",
                "memory_wait_controller_tiny_i17.fetch_done",
            ),
        )
        data_done = find_first_path(
            dut,
            (
                "tt_um_remedy_cpu.memory_wait_controller_tiny_i17.data_done",
                "memory_wait_controller_tiny_i17.data_done",
            ),
        )
        spi_ld = find_first_path(
            dut,
            (
                "tt_um_remedy_cpu.memory_wait_controller_tiny_i17.spi_ld",
                "memory_wait_controller_tiny_i17.spi_ld",
            ),
        )
        spi_st = find_first_path(
            dut,
            (
                "tt_um_remedy_cpu.memory_wait_controller_tiny_i17.spi_st",
                "memory_wait_controller_tiny_i17.spi_st",
            ),
        )
        pc = find_first_path(
            dut,
            (
                "tt_um_remedy_cpu.programCounter_i6.PCr",
                "programCounter_i6.PCr",
            ),
            ("PCr", "pc", "program_counter"),
        )
    except Exception as e:
        dut._log.warning("Could not bind explicit resync handles: %s", e)
        dut._qspi_test_resynced = True
        return

    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()
        if str(dut.rst_n.value) == "1":
            try:
                if int(init_done.value) == 1:
                    break
            except Exception:
                pass

    await RisingEdge(dut.clk)
    await ReadWrite()

    for h, value in (
        (cpu_state, 0),
        (mem_state, 0),
        (mem_op, 0),
        (mem_stall, 0),
        (fetch_done, 0),
        (data_done, 0),
        (spi_ld, 0),
        (spi_st, 0),
        (pc, 0),
    ):
        h.value = Force(value)

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await ReadWrite()

    for h in (cpu_state, mem_state, mem_op, mem_stall, fetch_done, data_done, spi_ld, spi_st, pc):
        h.value = Release()

    dut._qspi_test_resynced = True
    dut._log.info("QSPI test-side CPU/memory-wait resync done")


async def wait_execute_steps(
    dut,
    count: int,
    flash=None,
    timeout_ns: int = 2_000_000,
    settle_cycles: int = 32,
):
    """Gate-level-safe instruction wait helper.

    Preferred mode:
        await wait_execute_steps(dut, N, flash)

    In this mode we do NOT look at internal RTL signals like
    execute_now_pulse.  Instead, we wait until the external flash model has
    observed N non-literal instruction fetches on the SPI/QSPI pins.  This keeps
    the same test usable after synthesis/gate-level netlist generation, where
    hierarchy names and optimized internal signals may disappear.

    Fallback mode:
        await wait_execute_steps(dut, N)

    This keeps the old RTL-only behavior for older tests, but it can fail on
    gate-level simulations because it depends on internal signal names.
    """

    if flash is not None:
        # The memory model only fires instruction events when tracing is enabled.
        if hasattr(flash, "trace_fetch"):
            flash.trace_fetch = True

        async def _wait_from_flash():
            before_instr = getattr(flash, "instr_count", 0)
            before_words = getattr(flash, "fetch_word_count", 0)

            await flash.wait_instructions(count)

            after_instr = getattr(flash, "instr_count", 0)
            after_words = getattr(flash, "fetch_word_count", 0)
            dut._log.info(
                "FLASH EXEC WAIT: instr +%d/%d, words +%d",
                after_instr - before_instr,
                count,
                after_words - before_words,
            )

            # Fetch is visible at the flash pins slightly before the CPU's
            # architectural result is guaranteed visible.  A small fixed settle
            # delay makes this behave like the old execute-pulse wait without
            # relying on internal signals.
            for _ in range(settle_cycles):
                await RisingEdge(dut.clk)

        await with_timeout(_wait_from_flash(), timeout_ns, "ns")
        return

    # ------------------------------------------------------------------
    # Old RTL-only fallback.  Keep it for convenience, but do not use it
    # for gate-level tests.
    # ------------------------------------------------------------------
    await _resync_cpu_after_qspi_init(dut)

    try:
        exec_pulse = find_first_path(
            dut,
            (
                "tt_um_remedy_cpu.cpu_cycle_controller_tiny_i16.execute_now_pulse",
                "cpu_cycle_controller_tiny_i16.execute_now_pulse",
            ),
            ("execute_now_pulse", "execute-pulse"),
        )
    except Exception:
        exec_pulse = find_first_handle(dut, ("execute_now_pulse", "execute-pulse"))

    async def _wait_from_internal_exec_pulse():
        seen = 0
        while seen < count:
            await RisingEdge(dut.clk)
            await ReadOnly()

            if str(dut.rst_n.value) != "1":
                continue

            try:
                if int(exec_pulse.value) == 1:
                    seen += 1
                    dut._log.info("EXEC STEP %d/%d", seen, count)
            except Exception:
                pass

    await with_timeout(_wait_from_internal_exec_pulse(), timeout_ns, "ns")
