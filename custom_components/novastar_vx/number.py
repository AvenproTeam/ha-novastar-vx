"""Numbers that control the NovaStar VX controller: screen brightness."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NovaConfigEntry, NovaCoordinator
from .entity import NovaControlEntity, control_allowed


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NovaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the brightness number (only when control is allowed)."""
    if not control_allowed(hass, entry, Platform.NUMBER):
        return
    async_add_entities([Brightness(entry.runtime_data)])


class Brightness(NovaControlEntity, NumberEntity):
    """Brightness of the whole screen, in percent (the cards take 0-255 internally).

    The value shown is read from the first receiving card, since the controller
    sets all cards at once. If cards were set to different levels elsewhere
    (for example in NovaLCT), only the first one is shown.
    """

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coord: NovaCoordinator) -> None:
        super().__init__(coord, "brightness")

    @property
    def native_value(self) -> float | None:
        control = self._control
        if control is None or control.brightness is None:
            return None
        return round(control.brightness * 100 / 255)

    async def async_set_native_value(self, value: float) -> None:
        raw = round(value * 255 / 100)
        await self.coordinator.async_control(
            lambda: self.coordinator.client.set_brightness(raw), brightness=raw
        )
