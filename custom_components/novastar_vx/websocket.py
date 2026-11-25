"""Websocket API that feeds the screen map card."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .coordinator import NovaCoordinator
from .entity import card_label, card_problems, card_warnings, is_on_backup
from .protocol import model_name


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the websocket commands."""
    websocket_api.async_register_command(hass, ws_list_screens)
    websocket_api.async_register_command(hass, ws_subscribe_map)


def _loaded(hass: HomeAssistant) -> dict[str, NovaCoordinator]:
    return {
        e.entry_id: e.runtime_data
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    }


def build_map(coord: NovaCoordinator) -> dict[str, Any]:
    """Everything the card needs to draw one screen."""
    data, geo = coord.data, coord.geometry
    result: dict[str, Any] = {
        "title": coord.config_entry.title,
        "model": model_name(data.model_id) if data else None,
        "online": coord.last_update_success,
        "geometry": geo is not None,
        "width": geo.width if geo else None,
        "height": geo.height if geo else None,
        "outputs": [],
        "cards": [],
    }
    for port, count in sorted(coord.layout.items()):
        backup = next((b for m, b in (data.redundancy if data else []) if m == port), None)
        rect = geo.ports.get(port) if geo else None
        result["outputs"].append(
            {
                "output": port + 1,
                "cards": count,
                "backup_output": backup + 1 if backup is not None else None,
                "on_backup": is_on_backup(coord, port) if data else None,
                "rect": [rect.x, rect.y, rect.width, rect.height] if rect else None,
            }
        )
        for index in range(count):
            card = data.cards.get((port, index)) if data else None
            problems = card_problems(coord, card) if data else []
            warnings = card_warnings(coord, card) if data else []
            rect = geo.cards.get((port, index)) if geo else None
            result["cards"].append(
                {
                    "id": card_label(port, index),
                    "output": port + 1,
                    "index": index + 1,
                    "level": "error" if problems else "warning" if warnings else "ok",
                    "problems": problems,
                    "warnings": warnings,
                    "temperature": card.temperature if card else None,
                    "voltage": card.voltage if card else None,
                    "rect": [rect.x, rect.y, rect.width, rect.height] if rect else None,
                }
            )
    return result


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/screens"})
@callback
def ws_list_screens(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """List the configured controllers."""
    connection.send_result(
        msg["id"],
        [{"entry_id": k, "title": c.config_entry.title} for k, c in _loaded(hass).items()],
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/subscribe_map",
        vol.Optional("entry_id"): str,
    }
)
@callback
def ws_subscribe_map(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send the screen map now and after every poll."""
    screens = _loaded(hass)
    entry_id = msg.get("entry_id") or next(iter(screens), None)
    coord = screens.get(entry_id) if entry_id else None
    if coord is None:
        connection.send_error(msg["id"], "not_found", "No NovaStar controller is loaded")
        return

    @callback
    def _send() -> None:
        connection.send_message(websocket_api.event_message(msg["id"], build_map(coord)))

    connection.subscriptions[msg["id"]] = coord.async_add_listener(_send)
    connection.send_result(msg["id"])
    _send()
