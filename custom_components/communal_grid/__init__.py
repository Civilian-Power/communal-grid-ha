"""The Communal Grid integration."""
from __future__ import annotations

import logging
import pathlib

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import CommunalGridCoordinator
from .device_discovery_coordinator import DeviceDiscoveryCoordinator
from .vpp import VPPRegistry
from .der import DERRegistry

_LOGGER = logging.getLogger(__name__)

PLATFORMS_LIST: list[Platform] = [Platform.SENSOR]

_CARD_REGISTERED = False  # guard so we only register once across reloads


def _register_lovelace_card(hass: HomeAssistant) -> None:
    """Serve the custom Lovelace card JS and tell HA's frontend to load it.

    This runs once on first setup. The card then appears automatically in the
    HA dashboard card picker — no manual YAML or button-card required.
    """
    global _CARD_REGISTERED
    if _CARD_REGISTERED:
        return

    card_path = pathlib.Path(__file__).parent / "www" / "communal-grid-card.js"
    if not card_path.exists():
        _LOGGER.warning(
            "Communal Grid: card JS not found at %s — skipping card registration",
            card_path,
        )
        return

    url = "/communal_grid/communal-grid-card.js"

    # Serve the file as a static path
    hass.http.register_static_path(str(card_path.parent), str(card_path.parent))

    # Tell the HA frontend to load it (shows up in card picker)
    from homeassistant.components.frontend import add_extra_js_url
    add_extra_js_url(hass, url)

    _CARD_REGISTERED = True
    _LOGGER.debug("Communal Grid: registered Lovelace card at %s", url)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Communal Grid from a config entry."""
    _LOGGER.debug("Setting up Communal Grid integration for %s", entry.title)

    # Register the Lovelace card (no-op after first call)
    _register_lovelace_card(hass)

    # Create rate data coordinator (1-minute update cycle)
    rate_coordinator = CommunalGridCoordinator(hass, entry)
    await rate_coordinator.async_config_entry_first_refresh()

    # Create device discovery coordinator (5-minute scan cycle)
    device_discovery_coordinator = DeviceDiscoveryCoordinator(hass)
    await device_discovery_coordinator.async_config_entry_first_refresh()

    # Load VPP and DER registries (standalone JSON data files)
    vpp_registry = VPPRegistry()
    der_registry = DERRegistry()
    await hass.async_add_executor_job(vpp_registry.load)
    await hass.async_add_executor_job(der_registry.load)
    _LOGGER.debug(
        "Loaded %d VPP programs and %d DER types",
        len(vpp_registry.entries),
        len(der_registry.entries),
    )

    # Store coordinators and registries for sensor platform to access
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "rate": rate_coordinator,
        "device_discovery": device_discovery_coordinator,
        "vpp_registry": vpp_registry,
        "der_registry": der_registry,
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
