"""Async client for the NovaStar binary register protocol (TCP port 5200).

Request frame (multi-byte fields little endian):

    55 AA | ack | serial | src=FE | dst | device type | output port |
    card index (2) | code (0 read, 1 write) | reserved | address (4) |
    length (2) | data | checksum (2)

checksum = (sum of every byte after the 55 AA header + 0x5555) & 0xFFFF.
Replies start with AA 55 and have the same layout; ack == 0 means success.

This module only depends on the standard library, so it can be used and
tested on its own. It only ever sends read requests.
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass, field

DEV_SENDER = 0x00
DEV_RECEIVER = 0x01

# Register addresses, from the NovaLCT address map.
ADDR_MODEL_ID = 0x0000_0002
ADDR_SCANNER_ALL_MONITOR = 0x0A00_0000
LEN_SCANNER_ALL_MONITOR = 82
ADDR_SENDER_REDUNDANT_STATE = 0x0200_0098  # one byte per output
ADDR_SENDER_BACKUP_TABLE = 0x0230_0000  # main -> backup output pairs
ADDR_SENDER_PORT_AREA = 0x0200_00B1  # per output: width, height, x, y (u16) + 1 spare byte
PORT_AREA_STRIDE = 9
ADDR_SENDER_CARD_POSITION = 0x0300_0000  # per output block of (x, y) u16 pairs
CARD_POSITION_STRIDE = 0x1000
ADDR_SCANNER_SIZE = 0x0200_0017  # width, height (u16) of the area a card drives

MAX_PORTS = 16
MAX_CARDS_PER_PORT = 256

KNOWN_MODELS = {0x620C: "VX1000"}


class NovaError(Exception):
    """Raised when the controller can't be reached or the connection drops."""


def checksum(body: bytes) -> int:
    """Return the frame checksum for the bytes after the header."""
    return (sum(body) + 0x5555) & 0xFFFF


def build_read(serial: int, devtype: int, port: int, card: int, addr: int, length: int) -> bytes:
    """Build a read request frame."""
    body = (
        bytes([0x00, serial & 0xFF, 0xFE, 0x00, devtype, port])
        + struct.pack("<H", card)
        + bytes([0x00, 0x00])
        + struct.pack("<IH", addr, length)
    )
    return b"\x55\xaa" + body + struct.pack("<H", checksum(body))


def model_name(model_id: int | None) -> str:
    """Return a readable controller model name."""
    if model_id is None:
        return "Controller"
    return KNOWN_MODELS.get(model_id, f"Controller 0x{model_id:04X}")


@dataclass
class CardStatus:
    """Monitoring data for one receiving card."""

    port: int
    index: int
    online: bool
    temperature: float | None = None
    voltage: float | None = None
    humidity: int | None = None
    monitor_card_connected: bool = False
    module_status: bytes = b""
    raw: bytes = b""

    @property
    def module_flag(self) -> int | None:
        """Last byte of the module-status block (0xFF on most healthy cards)."""
        return self.module_status[-1] if self.module_status else None


@dataclass
class Rect:
    """A rectangle on the screen, in pixels."""

    x: int
    y: int
    width: int
    height: int


@dataclass
class ScreenGeometry:
    """Where every output and card sits on the screen."""

    width: int
    height: int
    ports: dict[int, Rect] = field(default_factory=dict)
    cards: dict[tuple[int, int], Rect] = field(default_factory=dict)


@dataclass
class ControllerStatus:
    """Result of one poll."""

    model_id: int
    redundancy: list[tuple[int, int]] = field(default_factory=list)
    redundant_state: dict[int, int] = field(default_factory=dict)
    backup_port_responding: dict[int, bool] = field(default_factory=dict)
    cards: dict[tuple[int, int], CardStatus] = field(default_factory=dict)


def decode_monitor(port: int, index: int, data: bytes) -> CardStatus:
    """Decode the 82-byte Scanner_AllMonitorData block of a receiving card."""
    temp = None
    if len(data) >= 2 and data[0] & 0x80:
        temp = (-0.5 if (data[0] & 0x7F) == 1 else 0.5) * data[1]
    humidity = data[2] & 0x7F if len(data) > 2 and data[2] & 0x80 else None
    voltage = round((data[3] & 0x7F) / 10, 1) if len(data) > 3 and data[3] & 0x80 else None
    return CardStatus(
        port=port,
        index=index,
        online=True,
        temperature=temp,
        voltage=voltage,
        humidity=humidity,
        monitor_card_connected=len(data) > 32 and data[32] == 1,
        module_status=bytes(data[11:27]),
        raw=bytes(data),
    )


def decode_redundancy(data: bytes) -> list[tuple[int, int]]:
    """Decode the backup table into (main output, backup output) pairs, 0-based.

    Layout seen on a VX1000: 4 header bytes, the pair count as a big-endian
    u16, then one big-endian (main u16, backup u16) entry per pair.
    """
    if len(data) < 6:
        return []
    count = int.from_bytes(data[4:6], "big")
    pairs = []
    for i in range(min(count, MAX_PORTS)):
        off = 6 + i * 4
        if off + 4 > len(data):
            break
        main = int.from_bytes(data[off : off + 2], "big")
        backup = int.from_bytes(data[off + 2 : off + 4], "big")
        if main < MAX_PORTS and backup < MAX_PORTS:
            pairs.append((main, backup))
    return pairs


class NovaClient:
    """Minimal async client. Sends one request at a time."""

    def __init__(self, host: str, port: int = 5200, timeout: float = 1.5) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._serial = 0
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Open the TCP connection if it isn't open."""
        if self._writer is not None:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout * 3
            )
        except (OSError, TimeoutError) as err:
            raise NovaError(f"Cannot connect to {self.host}:{self.port}: {err}") from err

    async def close(self) -> None:
        """Close the connection."""
        writer, self._reader, self._writer = self._writer, None, None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _read_frame(self) -> bytes:
        assert self._reader is not None
        while True:
            if await self._reader.readexactly(1) != b"\xaa":
                continue
            if await self._reader.readexactly(1) != b"\x55":
                continue
            head = await self._reader.readexactly(16)
            length = struct.unpack("<H", head[14:16])[0]
            rest = await self._reader.readexactly(length + 2)
            return b"\xaa\x55" + head + rest

    async def read(
        self, devtype: int, port: int, card: int, addr: int, length: int
    ) -> bytes | None:
        """Read a register block. Returns None when the device has no answer."""
        async with self._lock:
            await self.connect()
            assert self._writer is not None
            self._serial = (self._serial + 1) & 0xFF
            serial = self._serial
            try:
                self._writer.write(build_read(serial, devtype, port, card, addr, length))
                await self._writer.drain()
                while True:
                    frame = await asyncio.wait_for(self._read_frame(), self.timeout)
                    if frame[3] == serial:
                        break  # skip late replies to earlier requests
            except TimeoutError:
                return None
            except (OSError, asyncio.IncompleteReadError) as err:
                await self.close()
                raise NovaError(f"Connection lost: {err}") from err
        if frame[2] != 0:
            return None
        size = struct.unpack("<H", frame[16:18])[0]
        return frame[18 : 18 + size]

    async def read_model_id(self) -> int:
        """Read the controller's model id."""
        data = await self.read(DEV_SENDER, 0, 0, ADDR_MODEL_ID, 2)
        if data is None or len(data) < 2:
            raise NovaError("The controller did not answer the model id request")
        return int.from_bytes(data[:2], "little")

    async def discover(self) -> dict[int, int]:
        """Return {output port: number of receiving cards} by probing each index."""
        layout: dict[int, int] = {}
        for port in range(MAX_PORTS):
            count = 0
            while count < MAX_CARDS_PER_PORT:
                if not await self.read(DEV_RECEIVER, port, count, ADDR_MODEL_ID, 2):
                    break
                count += 1
            if count:
                layout[port] = count
        return layout

    async def read_card(self, port: int, index: int) -> CardStatus:
        """Read the monitoring block of one receiving card."""
        data = await self.read(
            DEV_RECEIVER, port, index, ADDR_SCANNER_ALL_MONITOR, LEN_SCANNER_ALL_MONITOR
        )
        if not data or len(data) < 27:
            return CardStatus(port=port, index=index, online=False)
        return decode_monitor(port, index, data)

    async def read_geometry(self, layout: dict[int, int]) -> ScreenGeometry | None:
        """Read where each output and card sits on the screen.

        Returns None if the controller doesn't expose a usable mapping.
        """
        ports: dict[int, Rect] = {}
        area = await self.read(
            DEV_SENDER, 0, 0, ADDR_SENDER_PORT_AREA, PORT_AREA_STRIDE * (max(layout) + 1)
        )
        for port in layout:
            off = port * PORT_AREA_STRIDE
            if area is None or off + 8 > len(area):
                return None
            w, h, x, y = struct.unpack("<HHHH", area[off : off + 8])
            if not w or not h or w == 0xFFFF:
                return None
            ports[port] = Rect(x, y, w, h)
        cards: dict[tuple[int, int], Rect] = {}
        for port, count in layout.items():
            table = await self.read(
                DEV_SENDER,
                0,
                0,
                ADDR_SENDER_CARD_POSITION + port * CARD_POSITION_STRIDE,
                count * 4,
            )
            if table is None or len(table) < count * 4:
                return None
            for index in range(count):
                cx, cy = struct.unpack("<HH", table[index * 4 : index * 4 + 4])
                size = await self.read(DEV_RECEIVER, port, index, ADDR_SCANNER_SIZE, 4)
                w, h = struct.unpack("<HH", size) if size and len(size) == 4 else (0, 0)
                if not w or not h or w == 0xFFFF:
                    w = h = 0  # card offline right now; sized from its neighbours below
                origin = ports[port]
                cards[(port, index)] = Rect(origin.x + cx, origin.y + cy, w, h)
        known = [r for r in cards.values() if r.width]
        if not known:
            return None
        for rect in cards.values():
            if not rect.width:
                rect.width, rect.height = known[0].width, known[0].height
        width = max(r.x + r.width for r in [*ports.values(), *cards.values()])
        height = max(r.y + r.height for r in [*ports.values(), *cards.values()])
        return ScreenGeometry(width, height, ports, cards)

    async def poll(self, layout: dict[int, int]) -> ControllerStatus:
        """Read the controller, its redundancy state and every expected card."""
        status = ControllerStatus(model_id=await self.read_model_id())
        table = await self.read(DEV_SENDER, 0, 0, ADDR_SENDER_BACKUP_TABLE, 64)
        status.redundancy = decode_redundancy(table or b"")
        state = await self.read(DEV_SENDER, 0, 0, ADDR_SENDER_REDUNDANT_STATE, 8) or b""
        for main, backup in status.redundancy:
            if main < len(state):
                status.redundant_state[main] = state[main]
            # While the main path is healthy, nothing answers on the backup output.
            reply = await self.read(DEV_RECEIVER, backup, 0, ADDR_MODEL_ID, 2)
            status.backup_port_responding[main] = bool(reply)
        for port, count in layout.items():
            for index in range(count):
                status.cards[(port, index)] = await self.read_card(port, index)
        return status
