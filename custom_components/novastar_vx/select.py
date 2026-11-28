"""Selects that control the NovaStar VX controller: video input and display mode."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NovaConfigEntry, NovaCoordinator
from .entity import NovaControlEntity, control_allowed
from .protocol import DISPLAY_MODES, INPUT_SOURCES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NovaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the control selects (only when control is allowed)."""
    if not control_allowed(hass, entry, Platform.SELECT):
        return
    coord = entry.runtime_data
    async_add_entities([InputSource(coord), DisplayMode(coord)])


def _name_of(table: dict[str, int], raw: int | None) -> str | None:
    return next((name for name, value in table.items() if value == raw), None)


class InputSource(NovaControlEntity, SelectEntity):
    """The video input the controller shows."""

    _attr_options = list(INPUT_SOURCES)

    def __init__(self, coord: NovaCoordinator) -> None:
        super().__init__(coord, "input_source")

    @property
    def current_option(self) -> str | None:
        control = self._control
        return _name_of(INPUT_SOURCES, control.input_source) if control else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        control = self._control
        raw = control.input_source if control else None
        return {"raw": f"0x{raw:02X}" if raw is not None else None}

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_control(
            lambda: self.coordinator.client.set_input_source(option),
            input_source=INPUT_SOURCES[option],
        )


class DisplayMode(NovaControlEntity, SelectEntity):
    """Normal picture, frozen picture, or black."""

    _attr_options = list(DISPLAY_MODES)

    def __init__(self, coord: NovaCoordinator) -> None:
        super().__init__(coord, "display_mode")

    @property
    def current_option(self) -> str | None:
        control = self._control
        return _name_of(DISPLAY_MODES, control.display_mode) if control else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        control = self._control
        raw = control.display_mode if control else None
        return {"raw": f"0x{raw:02X}" if raw is not None else None}

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_control(
            lambda: self.coordinator.client.set_display_mode(option),
            display_mode=DISPLAY_MODES[option],
        )
