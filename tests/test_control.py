"""Control entity tests, against the fake controller on localhost."""

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.novastar_vx.const import CONF_ALLOW_CONTROL
from custom_components.novastar_vx.protocol import (
    ADDR_SENDER_DISPLAY_MODE,
    ADDR_SENDER_INPUT_SOURCE,
)

from .fake_device import FakeController
from .test_init import _setup

CONTROL_ENTITIES = [
    "select.novastar_vx1000_input_source",
    "select.novastar_vx1000_display_mode",
    "switch.novastar_vx1000_freeze_image",
    "switch.novastar_vx1000_black_out",
    "switch.novastar_vx1000_picture_in_picture",
    "switch.novastar_vx1000_lock_front_panel",
    "number.novastar_vx1000_brightness",
]


async def test_no_control_entities_by_default(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    await _setup(hass, fake_controller)
    for entity_id in CONTROL_ENTITIES:
        assert hass.states.get(entity_id) is None
    assert fake_controller.writes == []


async def test_control_entities_show_state(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    await _setup(hass, fake_controller, **{CONF_ALLOW_CONTROL: True})
    assert hass.states.get("select.novastar_vx1000_input_source").state == "dvi"
    assert hass.states.get("select.novastar_vx1000_display_mode").state == "normal"
    assert hass.states.get("switch.novastar_vx1000_freeze_image").state == "off"
    assert hass.states.get("switch.novastar_vx1000_black_out").state == "off"
    assert hass.states.get("switch.novastar_vx1000_picture_in_picture").state == "off"
    assert hass.states.get("switch.novastar_vx1000_lock_front_panel").state == "off"
    assert hass.states.get("number.novastar_vx1000_brightness").state == "100"
    assert fake_controller.writes == []  # showing state never writes


async def test_control_commands(hass: HomeAssistant, fake_controller: FakeController) -> None:
    await _setup(hass, fake_controller, **{CONF_ALLOW_CONTROL: True})

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.novastar_vx1000_input_source", "option": "hdmi"},
        blocking=True,
    )
    assert fake_controller.control[ADDR_SENDER_INPUT_SOURCE] == b"\xa0"
    assert hass.states.get("select.novastar_vx1000_input_source").state == "hdmi"

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.novastar_vx1000_freeze_image"}, blocking=True
    )
    assert fake_controller.control[ADDR_SENDER_DISPLAY_MODE] == b"\x01"
    assert hass.states.get("switch.novastar_vx1000_freeze_image").state == "on"
    assert hass.states.get("select.novastar_vx1000_display_mode").state == "freeze"

    # Black replaces freeze, and "freeze off" then leaves the blackout alone.
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.novastar_vx1000_black_out"}, blocking=True
    )
    writes = len(fake_controller.writes)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.novastar_vx1000_freeze_image"}, blocking=True
    )
    assert len(fake_controller.writes) == writes
    assert fake_controller.control[ADDR_SENDER_DISPLAY_MODE] == b"\x02"
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.novastar_vx1000_black_out"}, blocking=True
    )
    assert fake_controller.control[ADDR_SENDER_DISPLAY_MODE] == b"\x00"

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.novastar_vx1000_brightness", "value": 50},
        blocking=True,
    )
    assert fake_controller.brightness == bytes([round(50 * 255 / 100)])
    assert hass.states.get("number.novastar_vx1000_brightness").state == "50"

    # The next poll reads the real values back.
    entry = hass.config_entries.async_entries("novastar_vx")[0]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("select.novastar_vx1000_input_source").state == "hdmi"
    assert hass.states.get("number.novastar_vx1000_brightness").state == "50"


async def test_failed_command_raises_and_keeps_state(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    await _setup(hass, fake_controller, **{CONF_ALLOW_CONTROL: True})
    fake_controller.reject_writes = True
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": "select.novastar_vx1000_display_mode", "option": "black"},
            blocking=True,
        )
    assert hass.states.get("select.novastar_vx1000_display_mode").state == "normal"


async def test_turning_control_off_removes_entities(
    hass: HomeAssistant, fake_controller: FakeController
) -> None:
    entry = await _setup(hass, fake_controller, **{CONF_ALLOW_CONTROL: True})
    assert hass.states.get("select.novastar_vx1000_input_source") is not None

    hass.config_entries.async_update_entry(entry, options={CONF_ALLOW_CONTROL: False})
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    for entity_id in CONTROL_ENTITIES:
        assert hass.states.get(entity_id) is None
        assert er.async_get(hass).async_get(entity_id) is None
    assert fake_controller.writes == []
