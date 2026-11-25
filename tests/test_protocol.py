"""Protocol tests against the fake controller."""

from custom_components.novastar_vx.protocol import (
    NovaClient,
    build_read,
    checksum,
    decode_monitor,
    decode_redundancy,
    model_name,
)

from .fake_device import BACKUP_TABLE, MONITOR_OK, FakeController


def test_build_read_matches_known_frame() -> None:
    frame = build_read(1, 0, 0, 0, 0x2, 2)
    assert frame.hex(" ") == "55 aa 00 01 fe 00 00 00 00 00 00 00 02 00 00 00 02 00 58 56"
    assert int.from_bytes(frame[-2:], "little") == checksum(frame[2:-2])


def test_decode_monitor() -> None:
    card = decode_monitor(0, 0, MONITOR_OK)
    assert card.temperature == 29.0
    assert card.voltage == 4.0
    assert card.humidity is None
    assert card.module_flag == 0xFF
    assert not card.monitor_card_connected


def test_decode_monitor_invalid_and_negative() -> None:
    card = decode_monitor(0, 0, bytes([0x81, 10, 0, 0x00]) + bytes(78))
    assert card.temperature == -5.0
    assert card.voltage is None
    assert decode_monitor(0, 0, bytes(82)).temperature is None


def test_decode_redundancy() -> None:
    assert decode_redundancy(BACKUP_TABLE) == [(0, 2), (1, 3)]
    assert decode_redundancy(b"") == []
    assert decode_redundancy(bytes(64)) == []


def test_model_name() -> None:
    assert model_name(0x620C) == "VX1000"
    assert model_name(0x1234) == "Controller 0x1234"


async def test_discover_and_poll(fake_controller: FakeController) -> None:
    client = NovaClient("127.0.0.1", fake_controller.port)
    try:
        assert await client.read_model_id() == 0x620C
        layout = await client.discover()
        assert layout == {0: 3, 1: 3}

        status = await client.poll(layout)
        assert status.redundancy == [(0, 2), (1, 3)]
        assert status.redundant_state == {0: 0x80, 1: 0x80}
        assert status.backup_port_responding == {0: False, 1: False}
        assert len(status.cards) == 6
        assert all(c.online and c.temperature == 29.0 for c in status.cards.values())

        # A card disappears.
        fake_controller.cards[1] = 2
        status = await client.poll(layout)
        assert not status.cards[(1, 2)].online
    finally:
        await client.close()


async def test_read_geometry(fake_controller: FakeController) -> None:
    client = NovaClient("127.0.0.1", fake_controller.port)
    try:
        geo = await client.read_geometry({0: 3, 1: 3})
    finally:
        await client.close()
    assert geo is not None
    assert (geo.width, geo.height) == (200, 300)
    assert geo.cards[(1, 2)].x == 100
    assert geo.cards[(1, 2)].y == 200
    assert geo.cards[(1, 2)].width == 100
