
import cocotb
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

# -----------------------------------------------------------------------------
# Gate-level detection
# -----------------------------------------------------------------------------

def is_gate_level():
    """Return True when Makefile passes +GATE_LEVEL to cocotb/simulator."""
    return "GATE_LEVEL" in cocotb.plusargs


# -----------------------------------------------------------------------------
# Gate-level-safe wait helpers
# -----------------------------------------------------------------------------

from cocotb.triggers import Timer, First


async def wait_execute_steps(
    dut,
    count: int,
    flash,
    timeout_ns: int = None,
    settle_cycles: int = 64,
    progress_ns: int = 1_000_000,
):
    """Wait for executed instructions using ONLY external flash traffic.

    This helper intentionally never reads internal RTL/gate signals such as
    execute_now_pulse, controller state, PC registers, or synthesized net names.

    Required usage:
        await wait_execute_steps(dut, N, flash)

    How it works:
      - The SPI/QSPI flash model observes real memory-pin transactions.
      - Each fetched non-literal word increments flash.instr_count.
      - This function waits until N additional non-literal instruction words are
        fetched, then waits a few clock cycles for outputs/registers to settle.

    Timeout behavior:
      - RTL sim defaults to 2 ms.
      - Gate-level sim defaults to 120 ms because the synthesized netlist may
        contain the real QSPI init delay.
    """

    if timeout_ns is None:
        timeout_ns = 120_000_000 if is_gate_level() else 2_000_000

    if flash is None:
        raise ValueError(
            "wait_execute_steps() requires the flash model: "
            "await wait_execute_steps(dut, count, flash). "
            "Internal execute signals are intentionally not supported."
        )

    if not hasattr(flash, "instr_count"):
        raise TypeError("flash model must expose instr_count")

    # Enable fetch tracing/event generation in the memory model.
    if hasattr(flash, "trace_fetch"):
        flash.trace_fetch = True

    start_instr = int(getattr(flash, "instr_count", 0))
    target_instr = start_instr + int(count)
    start_words = int(getattr(flash, "fetch_word_count", 0))

    dut._log.info(
        "FLASH EXEC WAIT: count=%d start_instr=%d target_instr=%d timeout=%dns gate=%s",
        count,
        start_instr,
        target_instr,
        timeout_ns,
        is_gate_level(),
    )

    async def _wait_from_flash():
        last_report_instr = start_instr
        last_report_words = start_words

        while int(getattr(flash, "instr_count", 0)) < target_instr:
            # Prefer the flash model's event if it exposes one. This avoids
            # polling internal DUT signals and also avoids busy waiting.
            if hasattr(flash, "_instr_event"):
                await First(flash._instr_event.wait(), Timer(progress_ns, units="ns"))
            else:
                await Timer(progress_ns, units="ns")

            now_instr = int(getattr(flash, "instr_count", 0))
            now_words = int(getattr(flash, "fetch_word_count", 0))

            # Progress log only when nothing changed during the last window.
            # This is very helpful for gate-level debugging without touching
            # internal synthesized names.
            if now_instr == last_report_instr and now_words == last_report_words:
                try:
                    cs = flash.pins.flash_cs
                    sclk = flash.pins.sclk
                except Exception:
                    cs = "?"
                    sclk = "?"
                dut._log.info(
                    "FLASH WAIT: instr=%d/%d words=%d last_word_addr=%s last_word=%s CS=%s SCLK=%s cont=%s",
                    now_instr - start_instr,
                    count,
                    now_words - start_words,
                    hex(getattr(flash, "last_fetch_word_addr", 0)) if getattr(flash, "last_fetch_word_addr", None) is not None else "None",
                    hex(getattr(flash, "last_fetch_word", 0)) if getattr(flash, "last_fetch_word", None) is not None else "None",
                    cs,
                    sclk,
                    getattr(flash, "continuous_enabled", "?"),
                )

            last_report_instr = now_instr
            last_report_words = now_words

        got_instr = int(getattr(flash, "instr_count", 0)) - start_instr
        got_words = int(getattr(flash, "fetch_word_count", 0)) - start_words
        dut._log.info("FLASH EXEC WAIT DONE: instr +%d/%d, words +%d", got_instr, count, got_words)

        for _ in range(int(settle_cycles)):
            await RisingEdge(dut.clk)

    await with_timeout(_wait_from_flash(), timeout_ns, "ns")
