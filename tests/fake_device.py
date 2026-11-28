"""A tiny fake NovaStar controller that speaks the TCP register protocol."""

from __future__ import annotations

import asyncio
import struct

from custom_components.novastar_vx.protocol import (
    ADDR_CARD_BRIGHTNESS,
    ADDR_MODEL_ID,
    ADDR_SCANNER_ALL_MONITOR,
    ADDR_SCANNER_SIZE,
    ADDR_SENDER_BACKUP_TABLE,
    ADDR_SENDER_CARD_POSITION,
    ADDR_SENDER_DISPLAY_MODE,
    ADDR_SENDER_INPUT_SOURCE,
    ADDR_SENDER_PANEL_LOCK,
    ADDR_SENDER_PIP,
    ADDR_SENDER_PORT_AREA,
    ADDR_SENDER_REDUNDANT_STATE,
    checksum,
)

# Healthy card: 29 °C, 4.0 V, module status ending in 0xFF.
MONITOR_OK = bytes.fromhex(
    "80 3a 00 a8 0d 00 00 00 00 00 00 10 06 01 08 02 00 10 32 54 76 98 ba dc fe e4 ff"
) + bytes(82 - 27)
BACKUP_TABLE = bytes.fromhex("9a 01 00 04 00 02 00 00 00 02 00 01 00 03") + bytes(50)
REDUNDANT_STATE = bytes.fromhex("80 80 00 00 00 ff 00 af")


class FakeController:
    """Two main outputs (0, 1) with backups (2, 3), and `cards` cards per output."""

    def __init__(self, cards: int = 3) -> None:
        self.cards = {0: cards, 1: cards}  # cards that answer
        self.configured = {0: cards, 1: cards}  # layout stored in the controller
        self.monitor: dict[tuple[int, int], bytes] = {}
        self.redundant_state = REDUNDANT_STATE
        self.backup_answers = False
        # Control registers (DVI input, normal picture, PIP off, panel unlocked).
        self.control = {
            ADDR_SENDER_INPUT_SOURCE: b"\x10",
            ADDR_SENDER_DISPLAY_MODE: b"\x00",
            ADDR_SENDER_PIP: b"\x00",
            ADDR_SENDER_PANEL_LOCK: b"\x00",
        }
        self.brightness = b"\xff"
        self.reject_writes = False
        # Every write received: (devtype, port, card, address, data, destination).
        self.writes: list[tuple[int, int, int, int, bytes, int]] = []
        self.server: asyncio.Server | None = None
        self.port = 0
        self._writers: set[asyncio.StreamWriter] = set()

    def register(self, devtype: int, port: int, card: int, addr: int) -> bytes | None:
        if devtype == 0 and addr == ADDR_SENDER_PORT_AREA:
            # Each output is a column of cards 100 px wide, side by side.
            return b"".join(
                struct.pack("<HHHHB", 100, 100 * self.configured[p], 100 * p, 0, 0) for p in (0, 1)
            )
        if devtype == 0 and addr & ~0xFFFF == ADDR_SENDER_CARD_POSITION:
            out = (addr - ADDR_SENDER_CARD_POSITION) // 0x1000
            return b"".join(
                struct.pack("<HH", 0, 100 * i) for i in range(self.configured.get(out, 0))
            )
        if devtype == 0:
            return {
                ADDR_MODEL_ID: b"\x0c\x62",
                ADDR_SENDER_BACKUP_TABLE: BACKUP_TABLE,
                ADDR_SENDER_REDUNDANT_STATE: self.redundant_state,
                **self.control,
            }.get(addr)
        main = port - 2 if self.backup_answers and port in (2, 3) else port
        if card >= self.cards.get(main, 0):
            return None
        if addr == ADDR_MODEL_ID:
            return b"\x04\x07"
        if addr == ADDR_SCANNER_SIZE:
            return struct.pack("<HH", 100, 100)
        if addr == ADDR_SCANNER_ALL_MONITOR:
            return self.monitor.get((main, card), MONITOR_OK)
        if addr == ADDR_CARD_BRIGHTNESS:
            return self.brightness
        return None

    def write(self, devtype: int, port: int, card: int, addr: int, data: bytes, dst: int) -> bool:
        """Apply a write. Returns whether it is acknowledged."""
        self.writes.append((devtype, port, card, addr, data, dst))
        if self.reject_writes:
            return False
        if devtype == 0 and addr in self.control:
            self.control[addr] = data
        elif devtype == 1 and addr == ADDR_CARD_BRIGHTNESS:
            self.brightness = data
        else:
            return False
        return True

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.add(writer)
        try:
            while True:
                req = await reader.readexactly(18)
                assert req[:2] == b"\x55\xaa"
                serial, dst, devtype, port = req[3], req[5], req[6], req[7]
                card = struct.unpack("<H", req[8:10])[0]
                code = req[10]
                addr, length = struct.unpack("<IH", req[12:18])
                if code == 1:  # a write carries its data after the header
                    req += await reader.readexactly(length + 2)
                    payload = req[18 : 18 + length]
                    assert struct.unpack("<H", req[-2:])[0] == checksum(req[2:-2])
                    ack = 0 if self.write(devtype, port, card, addr, payload, dst) else 1
                    data = b""
                    length = 0
                else:
                    req += await reader.readexactly(2)
                    assert struct.unpack("<H", req[18:20])[0] == checksum(req[2:18])
                    data = self.register(devtype, port, card, addr)
                    ack = 0 if data is not None else 1
                    data = (data or b"")[:length] if ack == 0 else b""
                body = (
                    bytes([ack, serial, 0x00, 0xFE, devtype, port])
                    + struct.pack("<H", card)
                    + bytes([0, 0])
                    + struct.pack("<IH", addr, len(data))
                    + data
                )
                writer.write(b"\xaa\x55" + body + struct.pack("<H", checksum(body)))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            self._writers.discard(writer)
            writer.close()

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        assert self.server is not None
        self.server.close()
        for writer in list(self._writers):
            writer.close()
        await self.server.wait_closed()
