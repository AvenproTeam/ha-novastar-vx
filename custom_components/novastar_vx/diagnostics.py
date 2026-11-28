"""Diagnostics for the NovaStar VX integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import NovaConfigEntry
from .entity import card_label

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NovaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coord = entry.runtime_data
    data = coord.data
    result: dict[str, Any] = {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "layout": coord.layout,
    }
    if data is None:
        return result
    cards = list(data.cards.values())
    if data.control is not None:
        # Raw register values: they show what a given firmware answers to the control registers.
        result["control_registers"] = {
            name: f"0x{value:02X}" if value is not None else None
            for name, value in vars(data.control).items()
        }
    result |= {
        "model_id": f"0x{data.model_id:04X}",
        "redundancy": [{"main": m + 1, "backup": b + 1} for m, b in data.redundancy],
        "redundant_state": {str(p + 1): f"0x{v:02X}" for p, v in data.redundant_state.items()},
        "backup_port_responding": {str(p + 1): v for p, v in data.backup_port_responding.items()},
        "offline_cards": [card_label(c.port, c.index) for c in cards if not c.online],
        # The raw monitoring block of the first card of each output helps decode new firmware.
        "sample_monitor_data": {
            card_label(c.port, c.index): c.raw.hex(" ") for c in cards if c.index == 0 and c.online
        },
        "module_status": {
            card_label(c.port, c.index): c.module_status.hex(" ") for c in cards if c.online
        },
    }
    return result
