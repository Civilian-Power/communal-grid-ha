"""Sensor entity for discovered controllable energy devices.

Exposes the count of devices that can be used to reduce power usage,
with per-category counts and full device details as attributes.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SENSOR_CONTROLLABLE_DEVICES,
    DEVICE_CAT_THERMOSTAT,
    DEVICE_CAT_SMART_PLUG,
    DEVICE_CAT_EV_CHARGER,
    DEVICE_CAT_WATER_HEATER,
    DEVICE_CAT_SMART_LIGHT,
    DEVICE_CAT_POWER_MONITOR,
)
from .device_discovery_coordinator import DeviceDiscoveryCoordinator

_LOGGER = logging.getLogger(__name__)


class ControllableDevicesSensor(
    CoordinatorEntity[DeviceDiscoveryCoordinator], SensorEntity
):
    """Sensor showing the count of controllable energy devices."""

    _attr_has_entity_name = True
    _attr_name = "Controllable Devices"
    _attr_icon = "mdi:devices"
    _attr_native_unit_of_measurement = "devices"

    def __init__(
        self,
        coordinator: DeviceDiscoveryCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the controllable devices sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_CONTROLLABLE_DEVICES}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to group under the Communal Grid device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Communal Grid",
        )

    @property
    def native_value(self) -> int | None:
        """Return the total number of controllable devices."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("total_devices", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return per-category counts and device details."""
        if self.coordinator.data is None:
            return {}

        data = self.coordinator.data
        attrs: dict[str, Any] = {
            "total_devices": data.get("total_devices", 0),
            "thermostat_count": data.get(f"{DEVICE_CAT_THERMOSTAT}_count", 0),
            "smart_plug_count": data.get(f"{DEVICE_CAT_SMART_PLUG}_count", 0),
            "ev_charger_count": data.get(f"{DEVICE_CAT_EV_CHARGER}_count", 0),
            "water_heater_count": data.get(f"{DEVICE_CAT_WATER_HEATER}_count", 0),
            "smart_light_count": data.get(f"{DEVICE_CAT_SMART_LIGHT}_count", 0),
            "power_monitor_count": data.get(f"{DEVICE_CAT_POWER_MONITOR}_count", 0),
            "thermostats": data.get(f"{DEVICE_CAT_THERMOSTAT}s", []),
            "smart_plugs": data.get(f"{DEVICE_CAT_SMART_PLUG}s", []),
            "ev_chargers": data.get(f"{DEVICE_CAT_EV_CHARGER}s", []),
            "water_heaters": data.get(f"{DEVICE_CAT_WATER_HEATER}s", []),
            "smart_lights": data.get(f"{DEVICE_CAT_SMART_LIGHT}s", []),
            "power_monitors": data.get(f"{DEVICE_CAT_POWER_MONITOR}s", []),
            "last_scan": data.get("last_scan"),
        }
        return attrs
