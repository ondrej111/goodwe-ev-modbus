from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

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
    SCAN_INTERVAL_IDLE,
    SCAN_INTERVAL_ACTIVE,
    READ_DELAY,
    RELEASE_WHEN_IDLE,
    ACTIVE_BACKOFF,
)
from .coordinator import GoodweEVCoordinator

PLATFORMS = ["binary_sensor", "sensor", "switch", "number", "select"]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    # Serve icon.png and icon@2x.png from this directory so HA's frontend
    # can display the brand icon on the integrations and devices pages.
    await hass.http.async_register_static_paths([
        StaticPathConfig(
            f"/api/custom_components/{DOMAIN}",
            str(Path(__file__).parent),
            cache_headers=True,
        )
    ])
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed polling options to the running coordinator.

    No reload: none of these three values affect which entities exist or how
    the Modbus socket is opened, so there is nothing to tear down. Reloading
    would drop and recreate every entity, briefly marking them unavailable and
    breaking the Modbus connection for no reason.

    Connection details (host, port, unit ID) are a different matter — those do
    need a new client — and are handled by the reconfigure flow, which reloads
    the entry itself.
    """
    coordinator: GoodweEVCoordinator | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )
    if coordinator is None:
        return
    options = entry.options
    coordinator.async_apply_options(
        scan_interval_idle=options.get(CONF_SCAN_INTERVAL_IDLE, SCAN_INTERVAL_IDLE),
        scan_interval_active=options.get(CONF_SCAN_INTERVAL_ACTIVE, SCAN_INTERVAL_ACTIVE),
        read_delay=options.get(CONF_READ_DELAY, READ_DELAY),
        release_when_idle=options.get(CONF_RELEASE_WHEN_IDLE, RELEASE_WHEN_IDLE),
        active_backoff=options.get(CONF_ACTIVE_BACKOFF, ACTIVE_BACKOFF),
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    options = entry.options
    coordinator = GoodweEVCoordinator(
        hass,
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_UNIT_ID],
        scan_interval_idle=options.get(CONF_SCAN_INTERVAL_IDLE, SCAN_INTERVAL_IDLE),
        scan_interval_active=options.get(CONF_SCAN_INTERVAL_ACTIVE, SCAN_INTERVAL_ACTIVE),
        read_delay=options.get(CONF_READ_DELAY, READ_DELAY),
        release_when_idle=options.get(CONF_RELEASE_WHEN_IDLE, RELEASE_WHEN_IDLE),
        active_backoff=options.get(CONF_ACTIVE_BACKOFF, ACTIVE_BACKOFF),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: GoodweEVCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.close()
    return unloaded
