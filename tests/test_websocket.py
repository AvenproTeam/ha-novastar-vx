"""Screen map websocket tests."""

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.novastar_vx.const import CONF_LAYOUT, DOMAIN

from .fake_device import MONITOR_OK, FakeController


async def test_screen_map(
    hass: HomeAssistant, fake_controller: FakeController, hass_ws_client
) -> None:
    fake_controller.monitor[(0, 0)] = MONITOR_OK[:26] + b"\x00" + MONITOR_OK[27:]
    fake_controller.cards[1] = 2
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="NovaStar VX1000",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: fake_controller.port,
            CONF_LAYOUT: {"0": 3, "1": 3},
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/screens"})
    msg = await client.receive_json()
    assert msg["result"] == [{"entry_id": entry.entry_id, "title": "NovaStar VX1000"}]

    await client.send_json({"id": 2, "type": f"{DOMAIN}/subscribe_map"})
    assert (await client.receive_json())["success"]
    event = (await client.receive_json())["event"]
    assert event["geometry"] is True
    assert (event["width"], event["height"]) == (200, 300)
    cards = {c["id"]: c for c in event["cards"]}
    assert cards["P1-001"]["level"] == "warning"
    assert cards["P1-001"]["warnings"] == ["module_flag"]
    assert cards["P1-002"]["level"] == "ok"
    assert cards["P2-003"]["level"] == "error"
    assert cards["P2-003"]["problems"] == ["offline"]
    assert cards["P2-002"]["rect"] == [100, 100, 100, 100]
    assert event["outputs"][0]["backup_output"] == 3

    # Updates are pushed after each poll.
    fake_controller.cards[1] = 3
    await entry.runtime_data.async_refresh()
    event = (await client.receive_json())["event"]
    assert {c["id"]: c for c in event["cards"]}["P2-003"]["level"] == "ok"

    await client.send_json({"id": 3, "type": f"{DOMAIN}/subscribe_map", "entry_id": "nope"})
    assert (await client.receive_json())["error"]["code"] == "not_found"
