"""Coordinator for periodic device discovery scans.

Runs independently from the rate data coordinator on a 5-minute interval,
scanning the HA entity and device registries for controllable energy devices.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, DEVICE_DISCOVERY_INTERVAL
from .device_discovery import DeviceDiscovery, DiscoveredDevice

_LOGGER = logging.getLogger(__name__)


class DeviceDiscoveryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that periodically scans for controllable energy devices."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the device discovery coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_device_discovery",
            update_interval=DEVICE_DISCOVERY_INTERVAL,
        )
        self._discovery = DeviceDiscovery(hass)

    async def _async_update_data(self) -> dict[str, Any]:
        """Scan for controllable energy devices."""
        try:
            categorized = await self._discovery.scan()
        except Exception as err:
            _LOGGER.error("Device discovery scan failed: %s", err)
            # If we have cached data, keep using it
            if self.data is not None:
                _LOGGER.warning("Using cached device discovery data")
                return self.data
            raise UpdateFailed(f"Device discovery failed: {err}") from err

        # Build the data dict with counts, device lists, and power totals
        total = 0
        total_power_w = 0.0
        total_annual_kwh = 0.0
        monitored_count = 0
        result: dict[str, Any] = {}

        for category, devices in categorized.items():
            count = len(devices)
            total += count
            result[f"{category}_count"] = count
            result[f"{category}s"] = [d.to_dict() for d in devices]

            # Sum up power data across all devices
            for device in devices:
                if device.current_power_w is not None:
                    total_power_w += device.current_power_w
                    monitored_count += 1
                if device.estimated_annual_kwh is not None:
                    total_annual_kwh += device.estimated_annual_kwh

        result["total_devices"] = total
        result["total_current_power_w"] = round(total_power_w, 1)
        result["total_estimated_annual_kwh"] = round(total_annual_kwh, 1)
        result["monitored_device_count"] = monitored_count
        result["last_scan"] = datetime.now().isoformat()

        _LOGGER.debug(
            "Device discovery found %d devices (%d with power monitoring, %.1f W total)",
            total, monitored_count, total_power_w,
        )
        return result
