from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import HomeAssistant, callback

from .const import (
    DOMAIN,
    CONF_HOST,
    CONF_PORT,
    CONF_UNIT_ID,
    CONF_SCAN_INTERVAL_IDLE,
    CONF_SCAN_INTERVAL_ACTIVE,
    CONF_READ_DELAY,
    CONF_RELEASE_WHEN_IDLE,
    CONF_ACTIVE_BACKOFF,
    DEFAULT_PORT,
    DEFAULT_UNIT_ID,
    SCAN_INTERVAL_IDLE,
    SCAN_INTERVAL_ACTIVE,
    READ_DELAY,
    RELEASE_WHEN_IDLE,
    ACTIVE_BACKOFF,
    MIN_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_READ_DELAY,
    MAX_READ_DELAY,
)


async def _test_connection(hass: HomeAssistant, host: str, port: int, unit_id: int) -> str | None:
    """Return error key or None on success."""
    def _connect():
        from pymodbus.client import ModbusTcpClient
        client = ModbusTcpClient(host, port=port, timeout=5)
        if not client.connect():
            return "cannot_connect"
        resp = client.read_holding_registers(10017, count=1, device_id=unit_id)
        client.close()
        if resp.isError():
            return "invalid_response"
        return None

    return await hass.async_add_executor_job(_connect)


def _connection_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Host/port/unit-id form, pre-filled with ``defaults`` when reconfiguring."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED)): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Required(
                CONF_UNIT_ID, default=defaults.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)
            ): int,
        }
    )


def _options_schema(options: dict[str, Any]) -> vol.Schema:
    """Polling form, pre-filled with the entry's current options."""
    interval = vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL))
    return vol.Schema(
        {
            vol.Required(
                CONF_SCAN_INTERVAL_ACTIVE,
                default=options.get(CONF_SCAN_INTERVAL_ACTIVE, SCAN_INTERVAL_ACTIVE),
            ): interval,
            vol.Required(
                CONF_SCAN_INTERVAL_IDLE,
                default=options.get(CONF_SCAN_INTERVAL_IDLE, SCAN_INTERVAL_IDLE),
            ): interval,
            vol.Required(
                CONF_READ_DELAY,
                default=options.get(CONF_READ_DELAY, READ_DELAY),
            ): vol.All(vol.Coerce(float), vol.Range(min=MIN_READ_DELAY, max=MAX_READ_DELAY)),
            vol.Required(
                CONF_ACTIVE_BACKOFF,
                default=options.get(CONF_ACTIVE_BACKOFF, ACTIVE_BACKOFF),
            ): interval,
            vol.Required(
                CONF_RELEASE_WHEN_IDLE,
                default=options.get(CONF_RELEASE_WHEN_IDLE, RELEASE_WHEN_IDLE),
            ): bool,
        }
    )


class GoodweEVConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "GoodweEVOptionsFlow":
        return GoodweEVOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            error = await _test_connection(
                self.hass,
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_UNIT_ID],
            )
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"GoodWe EV ({user_input[CONF_HOST]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_connection_schema(),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Change the charger's address, port or Modbus unit ID in place.

        Kept separate from the options flow because these values live in the
        entry's data, identify the device, and need a live connection test
        before they are accepted -- unlike the polling options, which are safe
        to apply blind.
        """
        entry = self._get_reconfigure_entry()
        errors = {}

        if user_input is not None:
            error = await _test_connection(
                self.hass,
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_UNIT_ID],
            )
            if error:
                errors["base"] = error
            else:
                unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                # The unique ID is derived from the address, so moving the
                # charger legitimately changes it. Only guard against landing
                # on an address another entry already owns.
                clash = any(
                    other.unique_id == unique_id and other.entry_id != entry.entry_id
                    for other in self.hass.config_entries.async_entries(DOMAIN)
                )
                if clash:
                    return self.async_abort(reason="already_configured")
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=unique_id,
                    title=f"GoodWe EV ({user_input[CONF_HOST]})",
                    data_updates=user_input,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_connection_schema(user_input or dict(entry.data)),
            errors=errors,
        )


class GoodweEVOptionsFlow(OptionsFlow):
    """Polling cadence and Modbus pacing, editable without re-adding the device."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(dict(self.config_entry.options)),
        )
