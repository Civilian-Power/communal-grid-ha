"""Device discovery for finding controllable energy devices in Home Assistant.

Scans the entity and device registries to find devices that can be
controlled to reduce power usage, such as thermostats, smart plugs,
EV chargers, water heaters, and smart lights.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, device_registry as dr

from .const import (
    DOMAIN,
    DEVICE_CAT_THERMOSTAT,
    DEVICE_CAT_SMART_PLUG,
    DEVICE_CAT_EV_CHARGER,
    DEVICE_CAT_WATER_HEATER,
    DEVICE_CAT_SMART_LIGHT,
    DEVICE_CAT_POWER_MONITOR,
    SMART_PLUG_MANUFACTURERS,
    EV_CHARGER_KEYWORDS,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class DiscoveredDevice:
    """Represents a discovered energy-relevant device."""

    entity_id: str
    name: str
    manufacturer: str | None
    model: str | None
    device_type: str
    has_power_monitoring: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for sensor attributes."""
        return asdict(self)


class DeviceDiscovery:
    """Discovers energy-relevant devices across all HA integrations."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize device discovery."""
        self._hass = hass

    async def scan(self) -> dict[str, list[DiscoveredDevice]]:
        """Scan HA registries and return categorized devices.

        Returns a dict mapping category names to lists of DiscoveredDevice.
        """
        ent_reg = er.async_get(self._hass)
        dev_reg = dr.async_get(self._hass)

        # Build a lookup of device_id -> device entry for fast access
        device_lookup: dict[str, dr.DeviceEntry] = {
            device.id: device for device in dev_reg.devices.values()
        }

        # Build a set of entity_ids that have power/energy monitoring sensors
        # (used to check if a switch also has power monitoring on the same device)
        power_device_ids: set[str] = set()
        for entity in ent_reg.entities.values():
            if entity.domain != "sensor" or entity.disabled:
                continue
            state = self._hass.states.get(entity.entity_id)
            if state and state.attributes.get("device_class") in ("power", "energy"):
                if entity.device_id:
                    power_device_ids.add(entity.device_id)

        results: dict[str, list[DiscoveredDevice]] = {
            DEVICE_CAT_THERMOSTAT: [],
            DEVICE_CAT_SMART_PLUG: [],
            DEVICE_CAT_EV_CHARGER: [],
            DEVICE_CAT_WATER_HEATER: [],
            DEVICE_CAT_SMART_LIGHT: [],
            DEVICE_CAT_POWER_MONITOR: [],
        }

        # Track which device_ids we've already categorized to avoid duplicates
        seen_device_ids: set[str] = set()

        for entity in ent_reg.entities.values():
            if entity.disabled:
                continue

            # Skip entities from our own integration
            if entity.platform == DOMAIN:
                continue

            device_entry = device_lookup.get(entity.device_id) if entity.device_id else None
            device_id = entity.device_id or entity.entity_id

            # Skip if we already categorized this device
            if device_id in seen_device_ids:
                continue

            state = self._hass.states.get(entity.entity_id)
            friendly_name = (
                (state.attributes.get("friendly_name") if state else None)
                or entity.name
                or entity.original_name
                or entity.entity_id
            )
            manufacturer = device_entry.manufacturer if device_entry else None
            model = device_entry.model if device_entry else None
            has_power = entity.device_id in power_device_ids if entity.device_id else False

            # Build searchable text for keyword matching
            search_text = " ".join(
                filter(None, [friendly_name, manufacturer, model, entity.entity_id])
            ).lower()

            # --- Check for EV charger first (most specific) ---
            if self._is_ev_charger(entity.domain, search_text):
                seen_device_ids.add(device_id)
                results[DEVICE_CAT_EV_CHARGER].append(
                    DiscoveredDevice(
                        entity_id=entity.entity_id,
                        name=friendly_name,
                        manufacturer=manufacturer,
                        model=model,
                        device_type=DEVICE_CAT_EV_CHARGER,
                        has_power_monitoring=has_power,
                    )
                )
                continue

            # --- Thermostats ---
            if entity.domain == "climate":
                seen_device_ids.add(device_id)
                results[DEVICE_CAT_THERMOSTAT].append(
                    DiscoveredDevice(
                        entity_id=entity.entity_id,
                        name=friendly_name,
                        manufacturer=manufacturer,
                        model=model,
                        device_type=DEVICE_CAT_THERMOSTAT,
                        has_power_monitoring=has_power,
                    )
                )
                continue

            # --- Water heaters ---
            if entity.domain == "water_heater":
                seen_device_ids.add(device_id)
                results[DEVICE_CAT_WATER_HEATER].append(
                    DiscoveredDevice(
                        entity_id=entity.entity_id,
                        name=friendly_name,
                        manufacturer=manufacturer,
                        model=model,
                        device_type=DEVICE_CAT_WATER_HEATER,
                        has_power_monitoring=has_power,
                    )
                )
                continue

            # --- Smart plugs ---
            if entity.domain == "switch" and self._is_smart_plug(
                entity, state, manufacturer
            ):
                seen_device_ids.add(device_id)
                results[DEVICE_CAT_SMART_PLUG].append(
                    DiscoveredDevice(
                        entity_id=entity.entity_id,
                        name=friendly_name,
                        manufacturer=manufacturer,
                        model=model,
                        device_type=DEVICE_CAT_SMART_PLUG,
                        has_power_monitoring=has_power,
                    )
                )
                continue

            # --- Smart lights ---
            if entity.domain == "light":
                seen_device_ids.add(device_id)
                results[DEVICE_CAT_SMART_LIGHT].append(
                    DiscoveredDevice(
                        entity_id=entity.entity_id,
                        name=friendly_name,
                        manufacturer=manufacturer,
                        model=model,
                        device_type=DEVICE_CAT_SMART_LIGHT,
                        has_power_monitoring=has_power,
                    )
                )
                continue

            # --- Power/energy monitors (sensors only, not switches) ---
            if entity.domain == "sensor" and state:
                device_class = state.attributes.get("device_class")
                if device_class in ("power", "energy"):
                    seen_device_ids.add(device_id)
                    results[DEVICE_CAT_POWER_MONITOR].append(
                        DiscoveredDevice(
                            entity_id=entity.entity_id,
                            name=friendly_name,
                            manufacturer=manufacturer,
                            model=model,
                            device_type=DEVICE_CAT_POWER_MONITOR,
                            has_power_monitoring=True,
                        )
                    )
                    continue

        for category, devices in results.items():
            _LOGGER.debug("Discovered %d %s devices", len(devices), category)

        return results

    @staticmethod
    def _is_ev_charger(domain: str, search_text: str) -> bool:
        """Check if an entity is an EV charger based on keywords."""
        if domain not in ("switch", "sensor", "binary_sensor", "number", "select"):
            return False
        return any(keyword in search_text for keyword in EV_CHARGER_KEYWORDS)

    @staticmethod
    def _is_smart_plug(
        entity: er.RegistryEntry,
        state: Any | None,
        manufacturer: str | None,
    ) -> bool:
        """Check if a switch entity is a smart plug.

        Matches on device_class=outlet or known smart plug manufacturers.
        """
        # Check device_class from state attributes
        if state and state.attributes.get("device_class") == "outlet":
            return True

        # Check against known manufacturers
        if manufacturer and manufacturer.lower() in SMART_PLUG_MANUFACTURERS:
            return True

        return False
