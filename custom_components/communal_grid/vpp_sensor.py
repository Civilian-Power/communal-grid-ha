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

# Population-weighted centroids for US states, DC, territories, and
# Canadian provinces. Used to derive user's state/province from HA
# home lat/lon coordinates without any external API call.
_US_STATE_CENTROIDS: dict[str, tuple[float, float]] = {
    "AL": (33.0, -86.8), "AK": (61.2, -149.9), "AZ": (33.5, -112.0),
    "AR": (34.8, -92.2), "CA": (36.8, -119.8), "CO": (39.7, -105.0),
    "CT": (41.6, -72.7), "DE": (39.2, -75.5), "FL": (28.1, -81.6),
    "GA": (33.3, -83.8), "HI": (21.3, -157.8), "ID": (43.6, -114.7),
    "IL": (40.0, -89.2), "IN": (39.8, -86.3), "IA": (41.9, -93.1),
    "KS": (38.5, -97.3), "KY": (38.0, -85.7), "LA": (30.5, -91.2),
    "ME": (44.0, -69.8), "MD": (39.0, -76.8), "MA": (42.3, -71.8),
    "MI": (42.7, -84.6), "MN": (45.0, -93.5), "MS": (32.4, -89.7),
    "MO": (38.6, -92.6), "MT": (46.9, -110.4), "NE": (41.1, -96.5),
    "NV": (39.5, -119.8), "NH": (43.2, -71.6), "NJ": (40.2, -74.7),
    "NM": (35.1, -106.6), "NY": (42.2, -74.8), "NC": (35.5, -79.4),
    "ND": (46.8, -100.8), "OH": (40.1, -82.7), "OK": (35.5, -97.5),
    "OR": (44.0, -121.0), "PA": (40.6, -77.2), "RI": (41.7, -71.5),
    "SC": (34.0, -81.0), "SD": (43.9, -99.4), "TN": (35.8, -86.3),
    "TX": (31.5, -97.0), "UT": (40.5, -111.9), "VT": (44.0, -72.7),
    "VA": (37.5, -78.9), "WA": (47.4, -121.3), "WV": (38.6, -80.6),
    "WI": (43.8, -89.4), "WY": (42.8, -107.6),
    "DC": (38.9, -77.0),
    "PR": (18.2, -66.5), "GU": (13.4, 144.8), "VI": (18.3, -64.8),
}

_CA_PROVINCE_CENTROIDS: dict[str, tuple[float, float]] = {
    "ON": (43.7, -79.4), "QC": (46.8, -71.2), "BC": (49.3, -123.1),
    "AB": (51.0, -114.1), "SK": (50.5, -104.6), "MB": (49.9, -97.1),
    "NB": (46.5, -66.5), "NS": (44.6, -63.6), "PE": (46.2, -63.0),
    "NL": (47.6, -52.7), "YT": (60.7, -135.0), "NT": (62.5, -114.4),
    "NU": (63.7, -68.5),
}


def _get_user_state(hass) -> str | None:
    """Derive the user's state/province code from HA home location.

    Uses hass.config.country to determine US vs Canada, then finds
    the nearest population-weighted centroid. No external API call.
    """
    lat = hass.config.latitude
    lon = hass.config.longitude
    if not lat or not lon:
        return None

    # Use HA country setting to pick the right centroid table.
    country = getattr(hass.config, "country", None) or ""
    if country.upper() == "CA":
        search = _CA_PROVINCE_CENTROIDS
    elif country.upper() in ("US", "USA", ""):
        # Default to US when country not set (most HA installs are US)
        search = _US_STATE_CENTROIDS
    else:
        # Unknown country — search both tables
        search = {**_US_STATE_CENTROIDS, **_CA_PROVINCE_CENTROIDS}

    best_state: str | None = None
    best_dist = float("inf")
    for code, (clat, clon) in search.items():
        dist = (lat - clat) ** 2 + (lon - clon) ** 2
        if dist < best_dist:
            best_dist = dist
            best_state = code

    _LOGGER.debug(
        "Derived user state from HA location (%.2f, %.2f, country=%s): %s",
        lat, lon, country, best_state,
    )
    return best_state

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

# Suffixes commonly appended to HA entity names for power/energy sensors.
# These are stripped to produce cleaner device names in VPP match results.
_NAME_SUFFIXES_TO_STRIP = [
    " Current consumption",
    " Power Minute Average",
    " Power",
    " Energy",
    " Current power",
    "_power_usage_today",
    " power_usage_today",
    " Today\u2019s Energy Production",
    " Today's Energy Production",
]


def _clean_device_name(name: str) -> str:
    """Remove common HA sensor suffixes from a device name."""
    for suffix in _NAME_SUFFIXES_TO_STRIP:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.strip()


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
        self._has_computed: bool = False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to group under the Communal Grid device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Communal Grid",
        )

    @property
    def native_value(self) -> int | None:
        """Return the count of matching VPP programs.

        Returns None (renders as 'unknown' in HA) until the first
        match computation finishes, so dashboard cards can show a
        loading state instead of '0 programs'.
        """
        if self.coordinator.data is None or not self._has_computed:
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

        # Derive user's state/province from HA home location
        user_state = _get_user_state(self.hass)

        # Get VPPs that serve this utility's region
        regional_vpps = self._vpp_registry.get_vpps_for_region(
            state=user_state,
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
        self._has_computed = True

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
                    "name": _clean_device_name(device.get("name", "Unknown")),
                    "manufacturer": device.get("manufacturer"),
                    "model": device.get("model"),
                    "der_type": der_type,
                    "current_power_w": device.get("current_power_w"),
                    "estimated_annual_kwh": device.get("estimated_annual_kwh"),
                })

        return devices
