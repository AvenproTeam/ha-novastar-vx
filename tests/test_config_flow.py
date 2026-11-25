"""Config flow tests."""

from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.novastar_vx.const import (
    CONF_CARD_ENTITIES,
    CONF_LAYOUT,
    CONF_RESCAN,
    CONF_SCAN_INTERVAL,
    CONF_TEMP_LIMIT,
    DOMAIN,
)

from .fake_device import FakeController


async def _add(hass: HomeAssistant, port: int):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: " 127.0.0.1 ", CONF_PORT: port}
    )


async def test_user_flow(hass: HomeAssistant, fake_controller: FakeController) -> None:
    result = await _add(hass, fake_controller.port)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "NovaStar VX1000"
    assert result["data"] == {
        CONF_HOST: "127.0.0.1",
        CONF_PORT: fake_controller.port,
        CONF_LAYOUT: {"0": 3, "1": 3},
    }
    await hass.async_block_till_done()

    # The same controller can't be added twice.
    result = await _add(hass, fake_controller.port)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_cannot_connect(hass: HomeAssistant, socket_enabled) -> None:
    result = await _add(hass, 1)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_no_cards(hass: HomeAssistant, fake_controller: FakeController) -> None:
    fake_controller.cards = {}
    result = await _add(hass, fake_controller.port)
    assert result["errors"] == {"base": "no_cards"}


async def test_options_and_rescan(hass: HomeAssistant, fake_controller: FakeController) -> None:
    entry = (await _add(hass, fake_controller.port))["result"]
    await hass.async_block_till_done()

    fake_controller.cards[1] = 5
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 60, CONF_TEMP_LIMIT: 55, CONF_CARD_ENTITIES: True, CONF_RESCAN: True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {CONF_SCAN_INTERVAL: 60, CONF_TEMP_LIMIT: 55, CONF_CARD_ENTITIES: True}
    assert entry.data[CONF_LAYOUT] == {"0": 3, "1": 5}
    assert entry.runtime_data.update_interval.total_seconds() == 60
    assert hass.states.get("sensor.novastar_vx1000_output_2_card_5_voltage").state == "4.0"


async def test_reconfigure(hass: HomeAssistant, fake_controller: FakeController) -> None:
    entry = (await _add(hass, fake_controller.port))["result"]
    await hass.async_block_till_done()

    other = FakeController(cards=1)
    await other.start()
    try:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: other.port}
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"
        assert entry.data[CONF_PORT] == other.port
        assert entry.data[CONF_LAYOUT] == {"0": 1, "1": 1}
        await hass.async_block_till_done()
        assert await hass.config_entries.async_unload(entry.entry_id)
    finally:
        await other.stop()
