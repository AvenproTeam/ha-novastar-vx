"""Config flow for the NovaStar VX integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .const import (
    CONF_CARD_ENTITIES,
    CONF_LAYOUT,
    CONF_RESCAN,
    CONF_SCAN_INTERVAL,
    CONF_TEMP_LIMIT,
    DEFAULT_CARD_ENTITIES,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TEMP_LIMIT,
    DOMAIN,
)
from .coordinator import NovaConfigEntry
from .protocol import NovaClient, NovaError, model_name


async def async_probe(host: str, port: int) -> tuple[int, dict[str, int]]:
    """Read the model id and scan the outputs for receiving cards."""
    client = NovaClient(host, port)
    try:
        model = await client.read_model_id()
        layout = await client.discover()
    finally:
        await client.close()
    return model, {str(k): v for k, v in layout.items()}


def _schema(host: str | None = None, port: int = DEFAULT_PORT) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=host or vol.UNDEFINED): str,
            vol.Required(CONF_PORT, default=port): vol.All(int, vol.Range(min=1, max=65535)),
        }
    )


class NovaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle adding a controller."""

    VERSION = 1

    async def _async_check(
        self, user_input: dict[str, Any], errors: dict[str, str]
    ) -> tuple[int, dict[str, int]] | None:
        try:
            model, layout = await async_probe(user_input[CONF_HOST], user_input[CONF_PORT])
        except NovaError:
            errors["base"] = "cannot_connect"
            return None
        if not layout:
            errors["base"] = "no_cards"
            return None
        return model, layout

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the controller's address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            if result := await self._async_check(user_input, errors):
                model, layout = result
                return self.async_create_entry(
                    title=f"NovaStar {model_name(model)}",
                    data={**user_input, CONF_LAYOUT: layout},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(_schema(), user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the controller's address."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_HOST] = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            if self.unique_id != entry.unique_id:
                self._abort_if_unique_id_configured()
            if result := await self._async_check(user_input, errors):
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=self.unique_id,
                    data={**entry.data, **user_input, CONF_LAYOUT: result[1]},
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(entry.data[CONF_HOST], entry.data[CONF_PORT]),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: NovaConfigEntry) -> NovaOptionsFlow:
        return NovaOptionsFlow()


class NovaOptionsFlow(OptionsFlow):
    """Polling, alert and entity options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.pop(CONF_RESCAN, False):
                try:
                    _model, layout = await async_probe(entry.data[CONF_HOST], entry.data[CONF_PORT])
                except NovaError:
                    errors["base"] = "cannot_connect"
                else:
                    if layout:
                        self.hass.config_entries.async_update_entry(
                            entry, data={**entry.data, CONF_LAYOUT: layout}
                        )
                    else:
                        errors["base"] = "no_cards"
            if not errors:
                return self.async_create_entry(data=user_input)
        opts = entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=10, max=3600)),
                vol.Required(
                    CONF_TEMP_LIMIT, default=opts.get(CONF_TEMP_LIMIT, DEFAULT_TEMP_LIMIT)
                ): vol.All(int, vol.Range(min=20, max=100)),
                vol.Required(
                    CONF_CARD_ENTITIES,
                    default=opts.get(CONF_CARD_ENTITIES, DEFAULT_CARD_ENTITIES),
                ): bool,
                vol.Required(CONF_RESCAN, default=False): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
