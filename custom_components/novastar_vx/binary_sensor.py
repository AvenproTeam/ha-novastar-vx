"""Binary sensors for the NovaStar VX integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_CARD_ENTITIES, DEFAULT_CARD_ENTITIES
from .coordinator import NovaConfigEntry, NovaCoordinator
from .entity import (
    NovaEntity,
    card_issues,
    card_label,
    card_problems,
    controller_device,
    is_on_backup,
    port_device,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NovaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coord = entry.runtime_data
    entities: list[BinarySensorEntity] = [Connection(coord), ScreenProblem(coord)]
    for main, backup in coord.data.redundancy:
        if main in coord.layout:
            entities.append(OutputOnBackup(coord, main, backup))
    card_entities = entry.options.get(CONF_CARD_ENTITIES, DEFAULT_CARD_ENTITIES)
    for port, count in coord.layout.items():
        entities.append(OutputProblem(coord, port))
        if card_entities:
            entities.extend(CardProblem(coord, port, i) for i in range(count))
    async_add_entities(entities)


class Connection(NovaEntity, BinarySensorEntity):
    """Whether the last poll reached the controller."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "connection"

    def __init__(self, coord: NovaCoordinator) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"{coord.config_entry.entry_id}_connection"
        self._attr_device_info = controller_device(coord)

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


class ScreenProblem(NovaEntity, BinarySensorEntity):
    """On when any card needs attention or any output runs on its backup."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "screen_problem"

    def __init__(self, coord: NovaCoordinator) -> None:
        super().__init__(coord)
        self._attr_unique_id = f"{coord.config_entry.entry_id}_screen_problem"
        self._attr_device_info = controller_device(coord)

    def _issues(self) -> dict[str, Any]:
        coord = self.coordinator
        return {
            "cards": card_issues(coord),
            "outputs_on_backup": [
                m + 1 for m, _ in coord.data.redundancy if is_on_backup(coord, m)
            ],
        }

    @property
    def is_on(self) -> bool:
        issues = self._issues()
        return bool(issues["cards"] or issues["outputs_on_backup"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._issues()


class OutputOnBackup(NovaEntity, BinarySensorEntity):
    """On when a main output is fed through its backup output."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "on_backup"

    def __init__(self, coord: NovaCoordinator, main: int, backup: int) -> None:
        super().__init__(coord)
        self.main, self.backup = main, backup
        self._attr_unique_id = f"{coord.config_entry.entry_id}_port{main}_on_backup"
        self._attr_device_info = port_device(coord, main)

    @property
    def is_on(self) -> bool | None:
        return is_on_backup(self.coordinator, self.main)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        state = data.redundant_state.get(self.main)
        return {
            "backup_output": self.backup + 1,
            "backup_path_responding": data.backup_port_responding.get(self.main),
            "redundant_state_raw": f"0x{state:02X}" if state is not None else None,
        }


class OutputProblem(NovaEntity, BinarySensorEntity):
    """On when any card on this output needs attention."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "card_problem_any"

    def __init__(self, coord: NovaCoordinator, port: int) -> None:
        super().__init__(coord)
        self.port = port
        self._attr_unique_id = f"{coord.config_entry.entry_id}_port{port}_problem"
        self._attr_device_info = port_device(coord, port)

    @property
    def is_on(self) -> bool:
        return bool(card_issues(self.coordinator, self.port))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"cards": card_issues(self.coordinator, self.port)}


class CardProblem(NovaEntity, BinarySensorEntity):
    """On when one card is offline or too hot."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "card_problem"

    def __init__(self, coord: NovaCoordinator, port: int, index: int) -> None:
        super().__init__(coord)
        self.port, self.index = port, index
        self._attr_translation_placeholders = {"card": str(index + 1)}
        self._attr_unique_id = f"{coord.config_entry.entry_id}_p{port}_c{index}_problem"
        self._attr_device_info = port_device(coord, port)

    @property
    def _card(self):
        return self.coordinator.data.cards.get((self.port, self.index))

    @property
    def is_on(self) -> bool:
        return bool(card_problems(self.coordinator, self._card))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        card = self._card
        attrs: dict[str, Any] = {
            "card": card_label(self.port, self.index),
            "problems": card_problems(self.coordinator, card),
        }
        if card is not None and card.online:
            flag = card.module_flag
            attrs["module_flag"] = f"0x{flag:02X}" if flag is not None else None
            attrs["module_status_raw"] = card.module_status.hex(" ")
            attrs["monitor_card_connected"] = card.monitor_card_connected
        return attrs
