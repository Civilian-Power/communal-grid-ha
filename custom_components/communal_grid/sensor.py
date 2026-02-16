"""Sensor entities for the Communal Grid integration.

Creates three sensors:
- Electric Rate: Current $/kWh based on TOU schedule
- Rate Tier: Current tier name (peak, off_peak, etc.)
- Gas Rate: Static gas rate from user config ($/therm or $/ccf)
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SENSOR_ELECTRIC_RATE,
    SENSOR_RATE_TIER,
    SENSOR_GAS_RATE,
    TIER_PEAK,
    TIER_PARTIAL_PEAK,
    TIER_OFF_PEAK,
    TIER_SUPER_OFF_PEAK,
)
from .coordinator import CommunalGridCoordinator

_LOGGER = logging.getLogger(__name__)

TIER_ICONS = {
    TIER_PEAK: "mdi:flash-alert",
    TIER_PARTIAL_PEAK: "mdi:flash",
    TIER_OFF_PEAK: "mdi:flash-outline",
    TIER_SUPER_OFF_PEAK: "mdi:battery-charging-low",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Communal Grid sensors from a config entry."""
    coordinator: CommunalGridCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        ElectricRateSensor(coordinator, entry),
        RateTierSensor(coordinator, entry),
    ]

    if coordinator.has_gas:
        entities.append(GasRateSensor(coordinator, entry))

    async_add_entities(entities)


class CommunalGridBaseSensor(CoordinatorEntity[CommunalGridCoordinator], SensorEntity):
    """Base class for Communal Grid sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CommunalGridCoordinator,
        entry: ConfigEntry,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{entry.entry_id}_{sensor_type}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info to group sensors under one device.

        Uses a fixed device name so entity IDs are always consistent
        regardless of which utility the user is on:
          - sensor.communal_grid_electric_rate
          - sensor.communal_grid_rate_tier
          - sensor.communal_grid_gas_rate
        """
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Communal Grid",
            manufacturer=self.coordinator.utility_name,
            model=self.coordinator.rate_plan_name,
            entry_type=None,
        )


class ElectricRateSensor(CommunalGridBaseSensor):
    """Sensor showing the current electricity rate in $/kWh."""

    _attr_name = "Electric Rate"
    _attr_icon = "mdi:flash"
    _attr_native_unit_of_measurement = "$/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: CommunalGridCoordinator, entry: ConfigEntry) -> None:
        """Initialize electric rate sensor."""
        super().__init__(coordinator, entry, SENSOR_ELECTRIC_RATE)

    @property
    def native_value(self) -> float | None:
        """Return the current electric rate."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("current_rate")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if self.coordinator.data is None:
            return {}
        data = self.coordinator.data
        return {
            "tier": data.get("tier", "unknown"),
            "season": data.get("season", "unknown"),
            "next_tier_change": data.get("next_change"),
            "utility": data.get("utility_name", ""),
            "rate_plan": data.get("rate_plan_name", ""),
            "last_api_update": data.get("last_api_fetch"),
        }


class RateTierSensor(CommunalGridBaseSensor):
    """Sensor showing the current rate tier (peak, off_peak, etc.)."""

    _attr_name = "Rate Tier"

    def __init__(self, coordinator: CommunalGridCoordinator, entry: ConfigEntry) -> None:
        """Initialize rate tier sensor."""
        super().__init__(coordinator, entry, SENSOR_RATE_TIER)

    @property
    def native_value(self) -> str | None:
        """Return the current tier name."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("tier")

    @property
    def icon(self) -> str:
        """Dynamic icon based on current tier."""
        tier = self.native_value or TIER_OFF_PEAK
        return TIER_ICONS.get(tier, "mdi:flash")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if self.coordinator.data is None:
            return {}
        data = self.coordinator.data
        return {
            "current_rate": data.get("current_rate"),
            "season": data.get("season", "unknown"),
            "next_tier_change": data.get("next_change"),
            "tier_display_name": _tier_display_name(data.get("tier", "")),
        }


class GasRateSensor(CommunalGridBaseSensor):
    """Sensor showing the configured gas rate."""

    _attr_name = "Gas Rate"
    _attr_icon = "mdi:fire"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: CommunalGridCoordinator, entry: ConfigEntry) -> None:
        """Initialize gas rate sensor."""
        super().__init__(coordinator, entry, SENSOR_GAS_RATE)

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the gas unit ($/therm or $/ccf)."""
        if self.coordinator.data is None:
            return "$/therm"
        unit = self.coordinator.data.get("gas_unit", "therm")
        return f"$/{unit}"

    @property
    def native_value(self) -> float | None:
        """Return the gas rate."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("gas_rate")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        if self.coordinator.data is None:
            return {}
        return {
            "unit_type": self.coordinator.data.get("gas_unit", "therm"),
            "note": "Manually configured rate (OpenEI does not provide gas rates)",
        }


def _tier_display_name(tier: str) -> str:
    """Convert tier ID to human-readable display name."""
    names = {
        TIER_PEAK: "Peak",
        TIER_PARTIAL_PEAK: "Partial Peak",
        TIER_OFF_PEAK: "Off-Peak",
        TIER_SUPER_OFF_PEAK: "Super Off-Peak",
    }
    return names.get(tier, tier.replace("_", " ").title())
