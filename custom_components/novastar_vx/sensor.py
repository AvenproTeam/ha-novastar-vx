"""Sensors for the NovaStar VX integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfElectricPotential, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_CARD_ENTITIES, DEFAULT_CARD_ENTITIES
from .coordinator import NovaConfigEntry, NovaCoordinator
from .entity import NovaEntity, card_label, controller_device, port_device
from .protocol import CardStatus

ONLINE = "cards_online"
MAX_TEMP = "max_temperature"
MIN_VOLT = "min_voltage"
FLAGGED = "module_flag"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NovaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coord = entry.runtime_data
    entities: list[SensorEntity] = [
        Summary(coord, None, kind) for kind in (ONLINE, MAX_TEMP, MIN_VOLT, FLAGGED)
    ]
    card_entities = entry.options.get(CONF_CARD_ENTITIES, DEFAULT_CARD_ENTITIES)
    for port, count in coord.layout.items():
        entities.extend(Summary(coord, port, kind) for kind in (ONLINE, MAX_TEMP, MIN_VOLT))
        if card_entities:
            for index in range(count):
                entities.append(CardValue(coord, port, index, "temperature"))
                entities.append(CardValue(coord, port, index, "voltage"))
    async_add_entities(entities)


def _set_unit(entity: SensorEntity, kind: str) -> None:
    if kind in (MAX_TEMP, "temperature"):
        entity._attr_device_class = SensorDeviceClass.TEMPERATURE
        entity._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    elif kind in (MIN_VOLT, "voltage"):
        entity._attr_device_class = SensorDeviceClass.VOLTAGE
        entity._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        entity._attr_suggested_display_precision = 1


class Summary(NovaEntity, SensorEntity):
    """A value summarised over all cards, or over the cards of one output."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coord: NovaCoordinator, port: int | None, kind: str) -> None:
        super().__init__(coord)
        self.port, self.kind = port, kind
        self._attr_translation_key = kind
        scope = "all" if port is None else f"port{port}"
        self._attr_unique_id = f"{coord.config_entry.entry_id}_{scope}_{kind}"
        self._attr_device_info = (
            controller_device(coord) if port is None else port_device(coord, port)
        )
        _set_unit(self, kind)

    def _cards(self) -> list[CardStatus]:
        return [
            c
            for (p, _), c in self.coordinator.data.cards.items()
            if self.port is None or p == self.port
        ]

    def _pick(self) -> CardStatus | None:
        online = [c for c in self._cards() if c.online]
        if self.kind == MAX_TEMP:
            vals = [c for c in online if c.temperature is not None]
            return max(vals, key=lambda c: c.temperature) if vals else None
        vals = [c for c in online if c.voltage is not None]
        return min(vals, key=lambda c: c.voltage) if vals else None

    @property
    def native_value(self) -> Any:
        cards = self._cards()
        if self.kind == ONLINE:
            return sum(c.online for c in cards)
        if self.kind == FLAGGED:
            return sum(1 for c in cards if c.online and c.module_flag not in (None, 0xFF))
        card = self._pick()
        if card is None:
            return None
        return card.temperature if self.kind == MAX_TEMP else card.voltage

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        cards = self._cards()
        if self.kind == ONLINE:
            layout = self.coordinator.layout
            expected = sum(layout.values()) if self.port is None else layout[self.port]
            return {
                "expected": expected,
                "offline_cards": [card_label(c.port, c.index) for c in cards if not c.online],
            }
        if self.kind == FLAGGED:
            return {
                "cards": {
                    card_label(c.port, c.index): f"0x{c.module_flag:02X}"
                    for c in cards
                    if c.online and c.module_flag not in (None, 0xFF)
                }
            }
        card = self._pick()
        return {"card": card_label(card.port, card.index)} if card else None


class CardValue(NovaEntity, SensorEntity):
    """Temperature or voltage of one receiving card."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coord: NovaCoordinator, port: int, index: int, kind: str) -> None:
        super().__init__(coord)
        self.port, self.index, self.kind = port, index, kind
        self._attr_translation_key = f"card_{kind}"
        self._attr_translation_placeholders = {"card": str(index + 1)}
        self._attr_unique_id = f"{coord.config_entry.entry_id}_p{port}_c{index}_{kind}"
        self._attr_device_info = port_device(coord, port)
        _set_unit(self, kind)

    @property
    def native_value(self) -> float | None:
        card = self.coordinator.data.cards.get((self.port, self.index))
        if card is None or not card.online:
            return None
        return card.temperature if self.kind == "temperature" else card.voltage
