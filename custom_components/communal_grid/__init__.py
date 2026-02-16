"""The Communal Grid integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import CommunalGridCoordinator
from .device_discovery_coordinator import DeviceDiscoveryCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS_LIST: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Communal Grid from a config entry."""
    _LOGGER.debug("Setting up Communal Grid integration for %s", entry.title)

    # Create rate data coordinator (1-minute update cycle)
    rate_coordinator = CommunalGridCoordinator(hass, entry)
    await rate_coordinator.async_config_entry_first_refresh()

    # Create device discovery coordinator (5-minute scan cycle)
    device_discovery_coordinator = DeviceDiscoveryCoordinator(hass)
    await device_discovery_coordinator.async_config_entry_first_refresh()

    # Store both coordinators for sensor platform to access
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "rate": rate_coordinator,
        "device_discovery": device_discovery_coordinator,
    }

    # Forward setup to sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS_LIST)

    # Listen for options updates (e.g., user changes gas rate)
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Communal Grid integration for %s", entry.title)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS_LIST)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update (e.g., gas rate change)."""
    await hass.config_entries.async_reload(entry.entry_id)
