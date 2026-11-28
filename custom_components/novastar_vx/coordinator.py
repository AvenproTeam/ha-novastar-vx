"""Polling coordinator for the NovaStar VX integration."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ALLOW_CONTROL,
    CONF_LAYOUT,
    CONF_SCAN_INTERVAL,
    DEFAULT_ALLOW_CONTROL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .protocol import ControllerStatus, ControlState, NovaClient, NovaError, ScreenGeometry

_LOGGER = logging.getLogger(__name__)

GEOMETRY_REFRESH = 600  # seconds; the layout only changes when someone edits it in NovaLCT

type NovaConfigEntry = ConfigEntry[NovaCoordinator]


class NovaCoordinator(DataUpdateCoordinator[ControllerStatus]):
    """Polls the controller and every receiving card."""

    config_entry: NovaConfigEntry

    def __init__(self, hass: HomeAssistant, entry: NovaConfigEntry, client: NovaClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.controller_device_id: str | None = None
        # Expected cards per output port (0-based). JSON keys are strings.
        self.layout: dict[int, int] = {int(k): v for k, v in entry.data[CONF_LAYOUT].items()}
        self.geometry: ScreenGeometry | None = None
        self._geometry_read = 0.0

    @property
    def allow_control(self) -> bool:
        """Whether the user turned on control (writing to the controller)."""
        return self.config_entry.options.get(CONF_ALLOW_CONTROL, DEFAULT_ALLOW_CONTROL)

    async def async_control(self, call: Callable[[], Awaitable[None]], **changes: int) -> None:
        """Send one control command and show its result at once.

        The next regular poll reads the real values back and corrects the state
        if the controller did not apply the change.
        """
        if not self.allow_control:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="control_disabled")
        try:
            await call()
        except NovaError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="control_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self.data.control = replace(self.data.control or ControlState(), **changes)
        self.async_update_listeners()

    async def _async_update_data(self) -> ControllerStatus:
        try:
            status = await self.client.poll(self.layout, control=self.allow_control)
            if time.monotonic() - self._geometry_read > GEOMETRY_REFRESH or self.geometry is None:
                self._geometry_read = time.monotonic()
                try:
                    self.geometry = await self.client.read_geometry(self.layout)
                except NovaError:
                    raise
                except Exception:  # an odd layout must never break monitoring
                    _LOGGER.exception("Could not read the screen layout")
                    self.geometry = None
            return status
        except NovaError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
