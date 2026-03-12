"""Communal Grid technical preview for Home Assistant."""
from __future__ import annotations

import logging
import pathlib
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, CoreState, EVENT_HOMEASSISTANT_STARTED
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN
from .coordinator import CommunalGridCoordinator
from .device_discovery_coordinator import DeviceDiscoveryCoordinator
from .vpp import VPPRegistry
from .der import DERRegistry

_LOGGER = logging.getLogger(__name__)

PLATFORMS_LIST: list[Platform] = [Platform.SENSOR]

CARD_URL_BASE = "/communal_grid"
CARD_FILENAME = "communal-grid-card.js"
CARD_VERSION = "1.0.5"  # Keep in sync with manifest.json version


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Communal Grid component.

    Card registration MUST happen here in async_setup (not async_setup_entry)
    so it runs exactly once and waits for Lovelace to be fully ready.
    """

    async def _register_frontend(_event: Any = None) -> None:
        """Register the static path and Lovelace resource."""

        # ── Step 1: Register the JS file as a static HTTP path ──────────────
        card_path = pathlib.Path(__file__).parent / "www" / CARD_FILENAME
        if not card_path.exists():
            _LOGGER.warning(
                "Communal Grid: card JS not found at %s — skipping registration",
                card_path,
            )
            return

        from homeassistant.components.http import StaticPathConfig

        static_url = f"{CARD_URL_BASE}/{CARD_FILENAME}"
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(CARD_URL_BASE, str(card_path.parent), False)]
            )
            _LOGGER.debug("Communal Grid: static path registered at %s", CARD_URL_BASE)
        except RuntimeError:
            # Already registered (e.g. during a reload) — that's fine
            _LOGGER.debug("Communal Grid: static path already registered, skipping")

        # ── Step 2: Wait for Lovelace resources to load, then persist ────────
        lovelace = hass.data.get("lovelace")
        if lovelace is None:
            _LOGGER.warning("Communal Grid: Lovelace data not found — card not registered")
            return

        if lovelace.mode != "storage":
            # YAML-mode dashboards: user must add resource manually
            _LOGGER.info(
                "Communal Grid: Lovelace is in YAML mode. Add this to your resources:\n"
                "  - url: %s?v=%s\n    type: module",
                static_url,
                CARD_VERSION,
            )
            return

        async def _check_and_register(_now: Any = None) -> None:
            """Poll until lovelace.resources is loaded, then register the card."""
            if not lovelace.resources.loaded:
                _LOGGER.debug("Communal Grid: Lovelace resources not yet loaded, retrying in 5s")
                async_call_later(hass, 5, _check_and_register)
                return

            versioned_url = f"{static_url}?v={CARD_VERSION}"
            base_url = static_url  # without ?v= for matching

            # Check if already registered (avoid duplicates on reload)
            existing = [
                r for r in lovelace.resources.async_items()
                if r["url"].startswith(base_url)
            ]

            if existing:
                resource = existing[0]
                current_version = resource["url"].split("?v=")[-1] if "?v=" in resource["url"] else "0"
                if current_version != CARD_VERSION:
                    # Update the URL to bust the cache with the new version
                    _LOGGER.info(
                        "Communal Grid: updating card resource from v%s to v%s",
                        current_version,
                        CARD_VERSION,
                    )
                    await lovelace.resources.async_update_item(
                        resource["id"],
                        {"res_type": "module", "url": versioned_url},
                    )
                else:
                    _LOGGER.debug(
                        "Communal Grid: card already registered at v%s, nothing to do",
                        CARD_VERSION,
                    )
            else:
                # First install — create the resource entry
                _LOGGER.info(
                    "Communal Grid: registering Lovelace card resource at %s",
                    versioned_url,
                )
                await lovelace.resources.async_create_item(
                    {"res_type": "module", "url": versioned_url}
                )

        await _check_and_register()

    # ── Trigger at the right time ─────────────────────────────────────────────
    # If HA is already fully running (e.g. integration reloaded from UI),
    # register immediately. Otherwise wait for the STARTED event so that
    # the http and frontend subsystems are guaranteed to be ready.
    if hass.state == CoreState.running:
        await _register_frontend()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register_frontend)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Communal Grid from a config entry."""
    _LOGGER.debug("Setting up Communal Grid integration for %s", entry.title)

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