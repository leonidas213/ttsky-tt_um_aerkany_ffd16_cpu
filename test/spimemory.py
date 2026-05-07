
from pathlib import Path
from collections import deque

from cocotb.triggers import RisingEdge, ValueChange, Event

from common import TTPins, find_first_handle

class MemoryImage:
    """Small byte-addressed memory API shared by flash/RAM models."""

    def __init__(self, size_bytes: int, fill: int = 0x00):
        self.size = int(size_bytes)
        self.mem = bytearray([fill & 0xFF] * self.size)

    def _mask_addr(self, addr: int) -> int:
        return int(addr) % self.size

    def load_bytes(self, data: bytes, base_addr: int = 0):
        base_addr = self._mask_addr(base_addr)
        data = bytes(data)
        for i, b in enumerate(data):
            self.mem[(base_addr + i) % self.size] = b

    def load_file(self, path, base_addr: int = 0):
        self.load_bytes(Path(path).read_bytes(), base_addr=base_addr)

    def poke8(self, addr: int, value: int):
        self.mem[self._mask_addr(addr)] = value & 0xFF

    def peek8(self, addr: int) -> int:
        return self.mem[self._mask_addr(addr)]

    def poke16(self, addr: int, value: int, little_endian: bool = False):
        addr = self._mask_addr(addr)
        value &= 0xFFFF
        lo = value & 0xFF
        hi = (value >> 8) & 0xFF
        if little_endian:
            self.mem[addr] = lo
            self.mem[(addr + 1) % self.size] = hi
        else:
            self.mem[addr] = hi
            self.mem[(addr + 1) % self.size] = lo

    def peek16(self, addr: int, little_endian: bool = False) -> int:
        addr = self._mask_addr(addr)
        b0 = self.mem[addr]
        b1 = self.mem[(addr + 1) % self.size]
        if little_endian:
            return b0 | (b1 << 8)
        return (b0 << 8) | b1

    def poke16w(self, word_addr: int, value: int, little_endian: bool = False):
        self.poke16((int(word_addr) & 0xFFFF) << 1, value, little_endian=little_endian)

    def peek16w(self, word_addr: int, little_endian: bool = False) -> int:
        return self.peek16((int(word_addr) & 0xFFFF) << 1, little_endian=little_endian)

    def load_words_w(self, word_addr: int, words, little_endian: bool = False):
        for i, word in enumerate(words):
            self.poke16w(word_addr + i, word, little_endian=little_endian)

    def load_word_map(self, word_map: dict[int, int], little_endian: bool = False):
        for word_addr, word in word_map.items():
            self.poke16w(word_addr, word, little_endian=little_endian)


class SpiMemoryDevice(MemoryImage):
    """Generic SPI memory target used for RAM and legacy SPI flash tests."""

    def __init__(
        self,
        dut,
        pins: TTPins,
        cs_bit: int,
        name: str,
        size_bytes: int = 65536,
        fill: int = 0x00,
        require_wren: bool = False,
        support_fast_read: bool = False,
        strict_upper_addr_zero: bool = True,
        verbose: bool = False,
        log_bytes: bool = False,
        trace_fetch: bool = False,
    ):
        super().__init__(size_bytes=size_bytes, fill=fill)
        self.dut = dut
        self.pins = pins
        self.cs_bit = cs_bit
        self.name = name
        self.require_wren = require_wren
        self.support_fast_read = support_fast_read
        self.strict_upper_addr_zero = strict_upper_addr_zero
        self.verbose = verbose
        self.log_bytes = log_bytes
        self.trace_fetch = trace_fetch

        self.write_enable = False
        self.prev_cs = 1
        self.prev_sclk = 0

        self.fetch_word_count = 0
        self.instr_count = 0
        self.literal_count = 0
        self.last_fetch_byte_addr = None
        self.last_fetch_word_addr = None
        self.last_fetch_word = None
        self._word_event = Event()
        self._instr_event = Event()

        self._clear_transaction_state()

    def _clear_transaction_state(self):
        self.cmd = None
        self.mode = None
        self.rx_shift = 0
        self.rx_count = 0
        self.tx_shift = 0
        self.tx_count = 0
        self.tx_queue = deque()
        self.addr_bytes = []
        self.addr = 0
        self.was_writing = False
        self._stream_start_addr = None
        self._stream_bytes_from_mem = 0

    def _log(self, msg, *args):
        if self.verbose:
            self.dut._log.info(f"[SPI-{self.name}] " + msg, *args)

    def _log_byte(self, direction: str, value: int):
        if self.verbose and self.log_bytes:
            self.dut._log.info("[SPI-%s] %s 0x%02X", self.name, direction, value & 0xFF)

    def _cs(self) -> int:
        return self.pins.out_bit(self.cs_bit)

    def _queue_byte(self, value: int):
        self.tx_queue.append(value & 0xFF)
        self._log_byte("QUEUE", value)

    def _status_reg(self) -> int:
        return 0x02 if self.write_enable else 0x00

    def _decode_24bit_addr(self, addr24: int) -> int:
        upper = (addr24 >> 16) & 0xFF
        if self.strict_upper_addr_zero:
            assert upper <= 1, (
                f"{self.name}: upper address byte must be <= 0x01, "
                f"got 0x{upper:02X} in 24-bit address 0x{addr24:06X}"
            )
        addr16 = addr24 & 0xFFFF
        self._log("ADDR24=0x%06X ADDR16=0x%04X", addr24, addr16)
        return addr16

    def _write_byte(self, addr: int, value: int):
        if self.require_wren and not self.write_enable:
            self.dut._log.warning(
                "%s: ignoring write to 0x%04X because WREN is not set",
                self.name,
                addr & 0xFFFF,
            )
            return
        self.poke8(addr, value)
        self._log("WRITE [0x%04X] = 0x%02X", addr & 0xFFFF, value & 0xFF)

    def _queue_mem_read_byte(self):
        byte_addr = self.addr & 0xFFFF
        self._queue_byte(self.peek8(byte_addr))
        self.addr = (self.addr + 1) & 0xFFFF
        self._stream_bytes_from_mem += 1
        self._trace_fetched_word_if_ready(byte_addr)

    def _trace_fetched_word_if_ready(self, last_byte_addr: int):
        if not self.trace_fetch:
            return
        if self.cmd not in (0x03, 0x0B, 0x0A, 0xEB):
            return
        if (self._stream_bytes_from_mem & 1) != 0:
            return

        word_start = (last_byte_addr - 1) & 0xFFFF
        if word_start & 1:
            self._log("Fetched word starts at odd byte address 0x%04X, ignoring", word_start)
            return

        word = self.peek16(word_start, little_endian=False)
        word_addr = word_start >> 1
        self.fetch_word_count += 1
        self.last_fetch_byte_addr = word_start
        self.last_fetch_word_addr = word_addr
        self.last_fetch_word = word
        self._log("FETCH word_addr=0x%04X word=0x%04X", word_addr, word)
        self._fire_word_event()

        if word & 0x8000:
            self.literal_count += 1
        else:
            self.instr_count += 1
            self._fire_instr_event()

    def _fire_word_event(self):
        old = self._word_event
        old.set()
        self._word_event = Event()

    def _fire_instr_event(self):
        old = self._instr_event
        old.set()
        self._instr_event = Event()

    async def wait_instructions(self, count: int = 1):
        target = self.instr_count + count
        while self.instr_count < target:
            evt = self._instr_event
            if self.instr_count >= target:
                break
            await evt.wait()

    async def wait_fetch_words(self, count: int = 1):
        target = self.fetch_word_count + count
        while self.fetch_word_count < target:
            evt = self._word_event
            if self.fetch_word_count >= target:
                break
            await evt.wait()

    async def step_instruction(self):
        await self.wait_instructions(1)
        return self.last_fetch_word_addr, self.last_fetch_word

    def _handle_rx_byte(self, byte: int):
        self._log_byte("RX", byte)

        if self.cmd is None:
            self.cmd = byte & 0xFF
            self._log("CMD 0x%02X", self.cmd)

            if self.cmd == 0x06 and self.require_wren:
                self.write_enable = True
                self.mode = "ignore"
            elif self.cmd == 0x04 and self.require_wren:
                self.write_enable = False
                self.mode = "ignore"
            elif self.cmd == 0x05:
                self.mode = "read_status"
                self._queue_byte(self._status_reg())
            elif self.cmd == 0x03:
                self.mode = "addr"
            elif self.cmd == 0x0B and self.support_fast_read:
                self.mode = "addr_fast"
            elif self.cmd == 0x02:
                self.mode = "addr_write"
            else:
                self.mode = "ignore"
                self.dut._log.warning("%s: unsupported SPI opcode 0x%02X", self.name, self.cmd)
            return

        if self.mode in ("addr", "addr_fast", "addr_write"):
            self.addr_bytes.append(byte & 0xFF)
            if len(self.addr_bytes) == 3:
                addr24 = (self.addr_bytes[0] << 16) | (self.addr_bytes[1] << 8) | self.addr_bytes[2]
                self.addr = self._decode_24bit_addr(addr24)
                if self.mode == "addr":
                    self.mode = "read_stream"
                    self._stream_start_addr = self.addr
                    self._stream_bytes_from_mem = 0
                    self._queue_mem_read_byte()
                elif self.mode == "addr_fast":
                    self.mode = "fast_dummy"
                else:
                    self.mode = "write_stream"
                    self.was_writing = True
            return

        if self.mode == "fast_dummy":
            self.mode = "read_stream"
            self._stream_start_addr = self.addr
            self._stream_bytes_from_mem = 0
            self._queue_mem_read_byte()
            return

        if self.mode == "read_stream":
            self._queue_mem_read_byte()
            return

        if self.mode == "read_status":
            self._queue_byte(self._status_reg())
            return

        if self.mode == "write_stream":
            self._write_byte(self.addr, byte)
            self.addr = (self.addr + 1) & 0xFFFF
            return

    def _on_spi_rising(self):
        bit = self.pins.mosi & 1
        self.rx_shift = ((self.rx_shift << 1) | bit) & 0xFF
        self.rx_count += 1
        if self.rx_count == 8:
            self._handle_rx_byte(self.rx_shift)
            self.rx_shift = 0
            self.rx_count = 0

    def _on_spi_falling(self):
        if self.tx_count == 0 and self.tx_queue:
            self.tx_shift = self.tx_queue.popleft()
            self.tx_count = 8
            self._log_byte("TX", self.tx_shift)

        if self.tx_count > 0:
            bit = (self.tx_shift >> 7) & 1
            self.pins.drive_miso(bit)
            self.tx_shift = (self.tx_shift << 1) & 0xFF
            self.tx_count -= 1
        else:
            self.pins.drive_miso(0)

    async def run(self):
        self._log("Starting SPI device process")
        self.pins.drive_miso(0)

        while True:
            await RisingEdge(self.dut.clk)
            if str(self.dut.rst_n.value) == "1":
                break

        self.prev_cs = 1
        self.prev_sclk = self.pins.sclk

        while True:
            await RisingEdge(self.dut.clk)
            cs = self._cs()
            sclk = self.pins.sclk
            if cs not in (0, 1) or sclk not in (0, 1):
                continue

            if cs == 1:
                if self.prev_cs == 0:
                    if self.require_wren and self.was_writing:
                        self.write_enable = False
                    self._clear_transaction_state()
                    self.pins.drive_miso(0)
                self.prev_cs = cs
                self.prev_sclk = sclk
                continue

            if self.prev_cs == 1 and cs == 0:
                self._clear_transaction_state()
                self._log("CS low -> begin transaction")

            if self.prev_sclk == 0 and sclk == 1:
                self._on_spi_rising()
            if self.prev_sclk == 1 and sclk == 0:
                self._on_spi_falling()

            self.prev_cs = cs
            self.prev_sclk = sclk


class SpiFlash(SpiMemoryDevice):
    """Legacy SPI flash model. Kept for older tests."""

    def __init__(self, dut, pins: TTPins, size_bytes: int = 65536, verbose: bool = False, log_bytes: bool = False):
        super().__init__(
            dut=dut,
            pins=pins,
            cs_bit=TTPins.SPI_FLASH_CS,
            name="flash",
            size_bytes=size_bytes,
            fill=0x00,
            require_wren=True,
            support_fast_read=True,
            strict_upper_addr_zero=True,
            verbose=verbose,
            log_bytes=log_bytes,
        )


class SpiRam(SpiMemoryDevice):
    def __init__(self, dut, pins: TTPins, size_bytes: int = 65536, verbose: bool = False, log_bytes: bool = False):
        super().__init__(
            dut=dut,
            pins=pins,
            cs_bit=TTPins.SPI_RAM_CS,
            name="ram",
            size_bytes=size_bytes,
            fill=0x00,
            require_wren=False,
            support_fast_read=False,
            strict_upper_addr_zero=True,
            verbose=verbose,
            log_bytes=log_bytes,
        )


class CSDeasserted(Exception):
    pass


class TTContinuousQSPIFlash(MemoryImage):
    """Flash model for your current qspi_memory_interface.

    Runtime protocol:
        CS low
        6 QSPI address nibbles
        2 QSPI mode nibbles, normally A0
        4 dummy clocks
        4 QSPI data nibbles = one 16-bit word
        CS high

    The default word_write_offset_bytes=2 keeps your temporary simulation offset
    patch.  Set it to 0 once the first-fetch/resync problem is fully fixed.
    """

    def __init__(
        self,
        dut,
        pins: TTPins,
        size_bytes: int = 1 << 20,
        name: str = "TT-CONT-QSPI-FLASH",
        strict_mode: bool = False,
        dummy_clocks: int = 4,
        word_write_offset_bytes: int = 2,
        verbose: bool = False,
        log_bytes: bool = False,
    ):
        super().__init__(size_bytes=size_bytes, fill=0x00)
        self.dut = dut
        self.pins = pins
        self.log = dut._log
        self.name = name
        self.strict_mode = strict_mode
        self.dummy_clocks = int(dummy_clocks)
        self.word_write_offset_bytes = int(word_write_offset_bytes)
        self.verbose = verbose
        self.log_bytes = log_bytes

        self.continuous_enabled = False
        self.trace_fetch = False
        self.fetch_word_count = 0
        self.instr_count = 0
        self.literal_count = 0
        self.last_fetch_byte_addr = None
        self.last_fetch_word_addr = None
        self.last_fetch_word = None
        self._word_event = Event()
        self._instr_event = Event()

    def _log(self, msg, *args):
        if self.verbose:
            self.dut._log.info(f"[{self.name}] " + msg, *args)

    # Override only word-address helpers for the current +0x02 simulation offset.
    def poke16w(self, word_addr: int, value: int, little_endian: bool = False):
        byte_addr = ((int(word_addr) & 0xFFFF) << 1) + self.word_write_offset_bytes
        self.poke16(byte_addr, value, little_endian=little_endian)

    def peek16w(self, word_addr: int, little_endian: bool = False) -> int:
        byte_addr = ((int(word_addr) & 0xFFFF) << 1) + self.word_write_offset_bytes
        return self.peek16(byte_addr, little_endian=little_endian)

    def load_words_w(self, word_addr: int, words, little_endian: bool = False):
        for i, word in enumerate(words):
            self.poke16w(word_addr + i, word, little_endian=little_endian)

    def load_word_map(self, word_map: dict[int, int], little_endian: bool = False):
        for word_addr, word in word_map.items():
            self.poke16w(word_addr, word, little_endian=little_endian)

    def cs_high(self) -> bool:
        return self.pins.flash_cs == 1

    def cs_low(self) -> bool:
        return self.pins.flash_cs == 0

    def release(self):
        self.pins.release_qspi()

    async def wait_cs_low(self):
        while self.cs_high():
            await ValueChange(self.dut.uio_out)

    async def wait_cs_high(self):
        while self.cs_low():
            await ValueChange(self.dut.uio_out)

    async def wait_sclk_rising(self):
        prev = self.pins.sclk
        while True:
            await ValueChange(self.dut.uio_out)
            if self.cs_high():
                raise CSDeasserted()
            now = self.pins.sclk
            if prev == 0 and now == 1:
                return
            prev = now

    async def wait_sclk_falling(self):
        prev = self.pins.sclk
        while True:
            await ValueChange(self.dut.uio_out)
            if self.cs_high():
                raise CSDeasserted()
            now = self.pins.sclk
            if prev == 1 and now == 0:
                return
            prev = now

    async def read_spi_byte(self) -> int:
        value = 0
        for _ in range(8):
            await self.wait_sclk_rising()
            value = (value << 1) | self.pins.mosi
        return value & 0xFF

    async def read_qspi_nibble(self) -> int:
        await self.wait_sclk_rising()
        return self.pins.qspi_out_nibble & 0xF

    async def read_qspi_nibbles(self, count: int, label: str = "qspi") -> int:
        value = 0
        nibbles = []
        for _ in range(count):
            nibble = await self.read_qspi_nibble()
            nibbles.append(nibble)
            value = (value << 4) | nibble
        self._log("%s nibbles=%s value=0x%X", label, nibbles, value)
        return value

    def _trace_word_fetch(self, byte_addr: int, word: int):
        if not self.trace_fetch:
            return

        logical_word_addr = (byte_addr - self.word_write_offset_bytes) >> 1
        self.fetch_word_count += 1
        self.last_fetch_byte_addr = byte_addr
        self.last_fetch_word_addr = logical_word_addr
        self.last_fetch_word = word & 0xFFFF
        self._log("FETCH byte_addr=0x%04X word_addr=0x%04X word=0x%04X", byte_addr, logical_word_addr, word)

        old = self._word_event
        old.set()
        self._word_event = Event()

        if word & 0x8000:
            self.literal_count += 1
        else:
            self.instr_count += 1
            old = self._instr_event
            old.set()
            self._instr_event = Event()

    async def wait_instructions(self, count: int = 1):
        target = self.instr_count + count
        while self.instr_count < target:
            evt = self._instr_event
            if self.instr_count >= target:
                break
            await evt.wait()

    async def wait_fetch_words(self, count: int = 1):
        target = self.fetch_word_count + count
        while self.fetch_word_count < target:
            evt = self._word_event
            if self.fetch_word_count >= target:
                break
            await evt.wait()

    async def step_instruction(self):
        await self.wait_instructions(1)
        return self.last_fetch_word_addr, self.last_fetch_word

    async def handle_runtime_read(self):
        raw_addr = await self.read_qspi_nibbles(6, "ADDR24")
        addr = raw_addr % self.size
        mode = await self.read_qspi_nibbles(2, "MODE")

        if self.strict_mode and mode != 0xA0:
            self.log.warning("[%s] expected mode A0, got 0x%02X", self.name, mode)

        await self.wait_sclk_falling()

        for _ in range(self.dummy_clocks):
            await self.wait_sclk_rising()
            await self.wait_sclk_falling()

        b0 = self.peek8(addr)
        b1 = self.peek8(addr + 1)
        word = (b0 << 8) | b1
        nibbles = [(b0 >> 4) & 0xF, b0 & 0xF, (b1 >> 4) & 0xF, b1 & 0xF]

        self._log("read addr=0x%06X mode=0x%02X word=0x%04X", raw_addr, mode, word)

        for nibble in nibbles:
            self.pins.drive_qspi_nibble(nibble)
            await self.wait_sclk_rising()
            await self.wait_sclk_falling()

        self._trace_word_fetch(addr, word)

        while self.cs_low():
            await ValueChange(self.dut.uio_out)

    async def handle_init_or_command(self):
        opcode = await self.read_spi_byte()
        self._log("init/SPI opcode 0x%02X", opcode)

        if opcode == 0xEB:
            self.continuous_enabled = True
            self.log.info("[%s] continuous QSPI mode enabled", self.name)

        await self.wait_cs_high()

    async def transaction(self):
        self.release()
        if self.continuous_enabled:
            await self.handle_runtime_read()
        else:
            await self.handle_init_or_command()

    async def _wait_reset_released_and_cs_idle(self):
        """Gate-level-safe startup for the flash model.

        At gate level, uio_out can be X during reset. TTPins.out_bit() treats
        X/Z as 0, which can look like CS low and start a fake transaction at
        time 0. Wait until reset is released and CS is observed idle-high before
        accepting the first real flash command.
        """
        self.release()

        while str(self.dut.rst_n.value) != "1":
            await RisingEdge(self.dut.clk)

        idle_cycles = 0
        while idle_cycles < 2:
            await RisingEdge(self.dut.clk)
            if str(self.dut.rst_n.value) != "1":
                idle_cycles = 0
            elif self.cs_high():
                idle_cycles += 1
            else:
                idle_cycles = 0

        self._log("reset released and flash CS idle-high observed")

    async def run(self):
        await self._wait_reset_released_and_cs_idle()

        while True:
            # If the DUT is reset again, throw away any partial transaction and
            # wait for a clean idle-high CS before listening again.
            if str(self.dut.rst_n.value) != "1":
                self.release()
                await self._wait_reset_released_and_cs_idle()

            await self.wait_cs_low()
            try:
                await self.transaction()
            except CSDeasserted:
                pass
            finally:
                self.release()


