"""Switches that control the NovaStar VX controller: freeze, black, PIP, panel lock."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NovaConfigEntry, NovaCoordinator
from .entity import NovaControlEntity, control_allowed
from .protocol import DISPLAY_MODES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NovaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the control switches (only when control is allowed)."""
    if not control_allowed(hass, entry, Platform.SWITCH):
        return
    coord = entry.runtime_data
    async_add_entities(
        [
            DisplayModeSwitch(coord, "freeze"),
            DisplayModeSwitch(coord, "black"),
            Pip(coord),
            PanelLock(coord),
        ]
    )


class DisplayModeSwitch(NovaControlEntity, SwitchEntity):
    """On while the screen is in one display mode (frozen, or black).

    Turning it off returns to the normal picture, but only if the screen is
    still in this mode, so "freeze off" can't undo a blackout set by someone else.
    """

    def __init__(self, coord: NovaCoordinator, mode: str) -> None:
        super().__init__(coord, mode)
        self.mode = mode

    @property
    def is_on(self) -> bool | None:
        control = self._control
        if control is None or control.display_mode is None:
            return None
        return control.display_mode == DISPLAY_MODES[self.mode]

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(self.mode)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.is_on is False:
            return
        await self._set("normal")

    async def _set(self, mode: str) -> None:
        await self.coordinator.async_control(
            lambda: self.coordinator.client.set_display_mode(mode),
            display_mode=DISPLAY_MODES[mode],
        )


class Pip(NovaControlEntity, SwitchEntity):
    """Picture-in-picture."""

    def __init__(self, coord: NovaCoordinator) -> None:
        super().__init__(coord, "pip")

    @property
    def is_on(self) -> bool | None:
        control = self._control
        return None if control is None or control.pip is None else bool(control.pip)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, on: bool) -> None:
        await self.coordinator.async_control(
            lambda: self.coordinator.client.set_pip(on), pip=int(on)
        )


class PanelLock(NovaControlEntity, SwitchEntity):
    """On while the controller's own LCD and buttons are locked."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coord: NovaCoordinator) -> None:
        super().__init__(coord, "panel_lock")

    @property
    def is_on(self) -> bool | None:
        control = self._control
        return None if control is None or control.panel_lock is None else bool(control.panel_lock)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, locked: bool) -> None:
        await self.coordinator.async_control(
            lambda: self.coordinator.client.set_panel_lock(locked), panel_lock=int(locked)
        )
