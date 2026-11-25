"""Setup and entity tests."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.novastar_vx.const import CONF_CARD_ENTITIES, CONF_LAYOUT, DOMAIN
from custom_components.novastar_vx.diagnostics import async_get_config_entry_diagnostics

from .fake_device import MONITOR_OK, FakeController


async def _setup(hass: HomeAssistant, device: FakeController, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="NovaStar VX1000",
        unique_id=f"127.0.0.1:{device.port}",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: device.port, CONF_LAYOUT: {"0": 3, "1": 3}},
        options=options,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_and_states(hass: HomeAssistant, fake_controller: FakeController) -> None:
    entry = await _setup(hass, fake_controller)
    assert entry.state is ConfigEntryState.LOADED

    assert hass.states.get("binary_sensor.novastar_vx1000_connection").state == "on"
    assert hass.states.get("binary_sensor.novastar_vx1000_screen_problem").state == "off"
    assert hass.states.get("sensor.novastar_vx1000_cards_online").state == "6"
    assert hass.states.get("sensor.novastar_vx1000_highest_card_temperature").state == "29.0"
    assert hass.states.get("sensor.novastar_vx1000_lowest_card_voltage").state == "4.0"
    assert hass.states.get("sensor.novastar_vx1000_output_1_card_3_temperature").state == "29.0"
    assert (
        hass.states.get("binary_sensor.novastar_vx1000_output_2_running_on_backup").state == "off"
    )
    assert hass.states.get("binary_sensor.novastar_vx1000_output_1_card_2_problem").state == "off"

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    controller = next(d for d in devices if (DOMAIN, entry.entry_id) in d.identifiers)
    assert controller.model == "VX1000"
    outputs = [d for d in devices if d.via_device_id == controller.id]
    assert sorted(d.name for d in outputs) == [
        "NovaStar VX1000 output 1",
        "NovaStar VX1000 output 2",
    ]

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_problems_detected(hass: HomeAssistant, fake_controller: FakeController) -> None:
    entry = await _setup(hass, fake_controller)
    coord = entry.runtime_data

    fake_controller.cards[1] = 2  # card P2-003 stops answering
    fake_controller.monitor[(0, 1)] = bytes([0x80, 160]) + MONITOR_OK[2:]  # 80 °C
    fake_controller.monitor[(0, 0)] = MONITOR_OK[:26] + b"\x00" + MONITOR_OK[27:]
    fake_controller.backup_answers = True  # output 1 now reached through output 3
    await coord.async_refresh()
    await hass.async_block_till_done()

    problem = hass.states.get("binary_sensor.novastar_vx1000_screen_problem")
    assert problem.state == "on"
    assert problem.attributes["cards"] == {
        "P1-002": ["over_temperature"],
        "P2-003": ["offline"],
    }
    assert problem.attributes["outputs_on_backup"] == [1, 2]
    assert hass.states.get("binary_sensor.novastar_vx1000_output_1_running_on_backup").state == "on"
    assert hass.states.get("sensor.novastar_vx1000_output_2_cards_online").state == "2"
    assert hass.states.get("sensor.novastar_vx1000_output_2_card_3_temperature").state == "unknown"
    assert hass.states.get("sensor.novastar_vx1000_cards_with_module_flag").state == "1"

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"]["data"][CONF_HOST] == "**REDACTED**"
    assert diag["offline_cards"] == ["P2-003"]


async def test_redundant_state_error(hass: HomeAssistant, fake_controller: FakeController) -> None:
    fake_controller.redundant_state = bytes.fromhex("81 80 00 00 00 ff 00 af")
    await _setup(hass, fake_controller)
    assert hass.states.get("binary_sensor.novastar_vx1000_output_1_running_on_backup").state == "on"
    assert (
        hass.states.get("binary_sensor.novastar_vx1000_output_2_running_on_backup").state == "off"
    )


async def test_without_card_entities(hass: HomeAssistant, fake_controller: FakeController) -> None:
    await _setup(hass, fake_controller, **{CONF_CARD_ENTITIES: False})
    assert hass.states.get("sensor.novastar_vx1000_output_1_cards_online").state == "3"
    assert hass.states.get("sensor.novastar_vx1000_output_1_card_1_temperature") is None


async def test_not_ready(hass: HomeAssistant, socket_enabled) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_LAYOUT: {"0": 1}},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
