"""The NovaStar VX LED controller integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from . import websocket
from .const import DOMAIN
from .coordinator import NovaConfigEntry, NovaCoordinator
from .entity import controller_device
from .protocol import NovaClient

# The control platforms are always forwarded; they add nothing unless control is allowed.
PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
CARD_URL = f"/{DOMAIN}/novastar-screen-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the screen map card and register its websocket API."""
    websocket.async_register(hass)
    if hass.http is not None and "frontend" in hass.config.components:
        card = Path(__file__).parent / "frontend" / "novastar-screen-card.js"
        await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(card), False)])
        version = (await async_get_integration(hass, DOMAIN)).version
        add_extra_js_url(hass, f"{CARD_URL}?v={version}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: NovaConfigEntry) -> bool:
    """Set up a controller from a config entry."""
    client = NovaClient(entry.data[CONF_HOST], entry.data[CONF_PORT])
    coordinator = NovaCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.close()
        raise
    # Register the controller first so the output devices can link to it.
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **controller_device(coordinator)
    )
    coordinator.controller_device_id = device.id
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: NovaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: NovaConfigEntry) -> bool:
    """Unload a config entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.client.close()
    return unloaded
