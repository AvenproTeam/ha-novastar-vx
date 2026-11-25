"""Shared entity helpers for the NovaStar VX integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_TEMP_LIMIT, DEFAULT_TEMP_LIMIT, DOMAIN
from .coordinator import NovaCoordinator
from .protocol import CardStatus, model_name


def controller_device(coord: NovaCoordinator) -> DeviceInfo:
    """Device info for the controller itself."""
    model_id = coord.data.model_id if coord.data else None
    return DeviceInfo(
        identifiers={(DOMAIN, coord.config_entry.entry_id)},
        name=coord.config_entry.title,
        manufacturer="NovaStar",
        model=model_name(model_id),
        model_id=f"0x{model_id:04X}" if model_id is not None else None,
    )


def port_device(coord: NovaCoordinator, port: int) -> DeviceInfo:
    """Device info for one Ethernet output and the cards behind it."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{coord.config_entry.entry_id}_port{port}")},
        translation_key="output",
        translation_placeholders={
            "controller": coord.config_entry.title,
            "output": str(port + 1),
        },
        manufacturer="NovaStar",
        model="Ethernet output",
        via_device_id=coord.controller_device_id,
    )


def card_label(port: int, index: int) -> str:
    """Short card name used in attributes, e.g. P1-008."""
    return f"P{port + 1}-{index + 1:03d}"


WARNING_MARGIN = 10  # °C below the alarm limit at which a card turns yellow


def card_problems(coord: NovaCoordinator, card: CardStatus | None) -> list[str]:
    """List why a card needs attention (empty when it's fine)."""
    if card is None or not card.online:
        return ["offline"]
    limit = coord.config_entry.options.get(CONF_TEMP_LIMIT, DEFAULT_TEMP_LIMIT)
    if card.temperature is not None and card.temperature >= limit:
        return ["over_temperature"]
    return []


def card_warnings(coord: NovaCoordinator, card: CardStatus | None) -> list[str]:
    """Things worth a look that aren't failures (yellow on the screen map)."""
    if card is None or not card.online:
        return []
    warnings = []
    limit = coord.config_entry.options.get(CONF_TEMP_LIMIT, DEFAULT_TEMP_LIMIT)
    if card.temperature is not None and limit - WARNING_MARGIN <= card.temperature < limit:
        warnings.append("high_temperature")
    if card.module_flag not in (None, 0xFF):
        warnings.append("module_flag")
    return warnings


def card_issues(coord: NovaCoordinator, port: int | None = None) -> dict[str, list[str]]:
    """Problems of every expected card, optionally for one output only."""
    issues = {}
    for p, count in coord.layout.items():
        if port is not None and p != port:
            continue
        for index in range(count):
            if problems := card_problems(coord, coord.data.cards.get((p, index))):
                issues[card_label(p, index)] = problems
    return issues


def is_on_backup(coord: NovaCoordinator, main: int) -> bool | None:
    """Whether a main output is being fed through its backup output."""
    data = coord.data
    if data is None:
        return None
    if data.backup_port_responding.get(main):
        return True
    state = data.redundant_state.get(main)
    if state is None or not state & 0x80:  # bit 7 = state valid
        return None
    return (state & 0x7F) != 0


class NovaEntity(CoordinatorEntity[NovaCoordinator]):
    """Base entity."""

    _attr_has_entity_name = True
