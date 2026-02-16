"""Sensor entity for VPP program matching.

Matches the user's configured utility and discovered devices against
the VPP registry to show which Virtual Power Plant programs are
available and which of the user's devices qualify for each.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_UTILITY_NAME,
    SENSOR_VPP_MATCHES,
    DEVICE_CAT_THERMOSTAT,
    DEVICE_CAT_SMART_PLUG,
    DEVICE_CAT_EV_CHARGER,
    DEVICE_CAT_WATER_HEATER,
    DEVICE_CAT_SMART_LIGHT,
    DEVICE_CAT_POWER_MONITOR,
)
from .der import DERRegistry
from .device_discovery_coordinator import DeviceDiscoveryCoordinator
from .vpp import VPPRegistry

_LOGGER = logging.getLogger(__name__)

# Map device_type from the Controllable Devices sensor to the category
# plurals used as keys in the coordinator data dict.
_CATEGORY_KEYS = [
    DEVICE_CAT_THERMOSTAT,
    DEVICE_CAT_SMART_PLUG,
    DEVICE_CAT_EV_CHARGER,
    DEVICE_CAT_WATER_HEATER,
    DEVICE_CAT_SMART_LIGHT,
    DEVICE_CAT_POWER_MONITOR,
]


class VPPMatchSensor(
    CoordinatorEntity[DeviceDiscoveryCoordinator], SensorEntity
):
    """Sensor showing VPP programs matching the user's utility and devices."""

    _attr_has_entity_name = True
    _attr_name = "VPP Matches"
    _attr_icon = "mdi:lightning-bolt-circle"
    _attr_native_unit_of_measurement = "programs"

    def __init__(
        self,
        coordinator: DeviceDiscoveryCoordinator,
        entry: ConfigEntry,
        vpp_registry: VPPRegistry,
        der_registry: DERRegistry,
    ) -> None:
        """Initialize the VPP match sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._vpp_registry = vpp_registry
        self._der_registry = der_registry
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_VPP_MATCHES}"
        self._match_results: list[dict[str, Any]] = []
        self._unmatched_count: int = 0

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to group under the Communal Grid device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Communal Grid",
        )

    @property
    def native_value(self) -> int | None:
        """Return the count of matching VPP programs."""
        if self.coordinator.data is None:
            return None
        return len(self._match_results)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return full VPP match details including per-VPP device lists."""
        if self.coordinator.data is None:
            return {}

        utility_name = self._entry.data.get(CONF_UTILITY_NAME, "Unknown")

        return {
            "utility_name": utility_name,
            "matching_vpp_count": len(self._match_results),
            "matching_vpps": self._match_results,
            "unmatched_device_count": self._unmatched_count,
            "last_updated": datetime.now().isoformat(),
        }

    def _handle_coordinator_update(self) -> None:
        """Recompute VPP matches when device discovery updates."""
        self._compute_matches()
        super()._handle_coordinator_update()

    def _compute_matches(self) -> None:
        """Run VPP matching against discovered devices.

        For each VPP in the registry:
        1. Check if it serves the user's utility region
        2. For each discovered device, check model-specific compatibility
        3. Collect matching devices with their power data
        """
        if self.coordinator.data is None:
            self._match_results = []
            self._unmatched_count = 0
            return

        utility_name = self._entry.data.get(CONF_UTILITY_NAME, "")

        # Gather all discovered devices from coordinator data
        all_devices = self._gather_devices()

        if not all_devices:
            self._match_results = []
            self._unmatched_count = 0
            return

        # Get VPPs that serve this utility's region
        regional_vpps = self._vpp_registry.get_vpps_for_region(
            utility=utility_name,
            active_only=True,
        )

        # Track which devices matched at least one VPP
        matched_device_ids: set[str] = set()
        results: list[dict[str, Any]] = []

        for vpp in regional_vpps:
            matching_devices: list[dict[str, Any]] = []
            total_power_w = 0.0
            total_annual_kwh = 0.0

            for device in all_devices:
                der_type = device["der_type"]
                manufacturer = device.get("manufacturer")
                model = device.get("model")

                # First try matching with the category-derived DER type
                matched_der_type = None
                matched_sd = None

                if vpp.supports_device(der_type, manufacturer, model):
                    matched_der_type = der_type
                    for sd in vpp.get_supported_devices_for_type(der_type):
                        if sd.matches_device(manufacturer, model):
                            matched_sd = sd
                            break
                else:
                    # Fallback: the device may be categorized under a
                    # different HA category than its real type (e.g., a
                    # KP115 smart plug appears as "power_monitor" because
                    # HA discovers its energy sensor, not its switch).
                    # Check this VPP's supported_devices entries that have
                    # a SPECIFIC manufacturer (not wildcard) — if the
                    # manufacturer+model matches, use that entry's DER type.
                    # We skip wildcard entries here to avoid false positives
                    # (e.g., a Lutron dimmer matching a wildcard thermostat).
                    for sd in vpp.supported_devices:
                        if sd.manufacturer == "*":
                            continue
                        if sd.matches_device(manufacturer, model):
                            matched_der_type = sd.der_type
                            matched_sd = sd
                            break

                if matched_der_type is None:
                    continue

                notes = matched_sd.notes if matched_sd else None
                power_w = device.get("current_power_w") or 0.0
                annual_kwh = device.get("estimated_annual_kwh") or 0.0

                matching_devices.append({
                    "name": device["name"],
                    "manufacturer": manufacturer,
                    "model": model,
                    "der_type": matched_der_type,
                    "estimated_annual_kwh": annual_kwh,
                    "current_power_w": power_w,
                    "notes": notes,
                })

                total_power_w += power_w
                total_annual_kwh += annual_kwh
                matched_device_ids.add(device["entity_id"])

            if matching_devices:
                results.append({
                    "id": vpp.id,
                    "name": vpp.name,
                    "provider": vpp.provider,
                    "description": vpp.description,
                    "enrollment_url": vpp.enrollment_url,
                    "management_url": vpp.management_url,
                    "reward": vpp.reward.to_dict(),
                    "matching_devices": matching_devices,
                    "matching_device_count": len(matching_devices),
                    "total_matching_power_w": round(total_power_w, 1),
                    "total_matching_annual_kwh": round(total_annual_kwh, 1),
                })

        self._match_results = results
        self._unmatched_count = len(all_devices) - len(matched_device_ids)

    def _gather_devices(self) -> list[dict[str, Any]]:
        """Gather all discovered devices and resolve their DER type IDs.

        The device_discovery coordinator stores devices by category
        (e.g., "thermostats", "smart_plugs"). Each device dict has a
        "device_type" field matching an HA device category. We map this
        to a DER type ID using the DER registry.

        Returns:
            List of device dicts with "der_type" added.
        """
        data = self.coordinator.data
        if not data:
            return []

        devices: list[dict[str, Any]] = []

        for category in _CATEGORY_KEYS:
            # Coordinator stores device lists with plural key (e.g., "thermostats")
            category_devices = data.get(f"{category}s", [])

            for device in category_devices:
                device_type = device.get("device_type", category)

                # Map HA device category → DER type ID(s)
                der_entries = self._der_registry.get_by_ha_category(device_type)
                if not der_entries:
                    # No DER mapping — skip (e.g., power_monitor with no VPP role)
                    continue

                # Use the first matching DER type
                # (most categories map to exactly one DER type)
                der_type = der_entries[0].id

                devices.append({
                    "entity_id": device.get("entity_id", ""),
                    "name": device.get("name", "Unknown"),
                    "manufacturer": device.get("manufacturer"),
                    "model": device.get("model"),
                    "der_type": der_type,
                    "current_power_w": device.get("current_power_w"),
                    "estimated_annual_kwh": device.get("estimated_annual_kwh"),
                })

        return devices
