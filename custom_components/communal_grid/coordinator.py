"""Data coordinator for Communal Grid integration.

Manages periodic rate recalculation (every minute) and daily API fetches
from OpenEI to keep the rate schedule fresh.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    UPDATE_INTERVAL,
    API_FETCH_INTERVAL,
    CONF_API_KEY,
    CONF_UTILITY_ID,
    CONF_RATE_PLAN_ID,
    CONF_RATE_PLAN_NAME,
    CONF_UTILITY_NAME,
    CONF_GAS_RATE,
    CONF_GAS_UNIT,
    CONF_CONFIGURE_GAS,
    DEFAULT_GAS_RATE,
    DEFAULT_GAS_UNIT,
)
from .openei_client import OpenEIClient, OpenEIError
from .rate_calculator import RateCalculator, RateSchedule, parse_openei_schedule

_LOGGER = logging.getLogger(__name__)


class CommunalGridCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that manages rate data updates.

    Updates flow:
    - Every 1 minute: Recalculate current rate from cached schedule
    - Every 24 hours: Fetch fresh rate schedule from OpenEI API
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=UPDATE_INTERVAL,
        )

        self._entry = entry
        self._api_key: str = entry.data[CONF_API_KEY]
        self._utility_id: str = entry.data[CONF_UTILITY_ID]
        self._rate_plan_id: str = entry.data[CONF_RATE_PLAN_ID]
        self._utility_name: str = entry.data.get(CONF_UTILITY_NAME, "Unknown")
        self._rate_plan_name: str = entry.data.get(CONF_RATE_PLAN_NAME, "Unknown")

        # Gas config
        self._configure_gas: bool = entry.data.get(CONF_CONFIGURE_GAS, False)
        self._gas_rate: float = entry.data.get(CONF_GAS_RATE, DEFAULT_GAS_RATE)
        self._gas_unit: str = entry.data.get(CONF_GAS_UNIT, DEFAULT_GAS_UNIT)

        # Internal state
        self._client: OpenEIClient | None = None
        self._schedule: RateSchedule | None = None
        self._calculator: RateCalculator | None = None
        self._last_api_fetch: datetime | None = None

    @property
    def has_gas(self) -> bool:
        """Whether gas rate is configured."""
        return self._configure_gas

    @property
    def utility_name(self) -> str:
        """The utility company name."""
        return self._utility_name

    @property
    def rate_plan_name(self) -> str:
        """The rate plan name."""
        return self._rate_plan_name

    def _get_client(self) -> OpenEIClient:
        """Get or create the API client (lazy init)."""
        if self._client is None:
            session = async_get_clientsession(self.hass)
            self._client = OpenEIClient(session, self._api_key)
        return self._client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data and calculate current rate."""
        now = dt_util.now()

        needs_fetch = (
            self._schedule is None
            or self._last_api_fetch is None
            or (now - self._last_api_fetch) >= API_FETCH_INTERVAL
        )

        if needs_fetch:
            try:
                await self._fetch_rate_schedule()
            except OpenEIError as err:
                if self._schedule is not None:
                    _LOGGER.warning(
                        "Failed to refresh rate schedule from OpenEI, "
                        "using cached data (last fetch: %s): %s",
                        self._last_api_fetch, err,
                    )
                else:
                    raise UpdateFailed(
                        f"Failed to fetch rate schedule from OpenEI: {err}"
                    ) from err

        if self._calculator is None:
            raise UpdateFailed("No rate schedule available")

        try:
            current = self._calculator.get_current_rate(now)
        except Exception as err:
            raise UpdateFailed(f"Error calculating current rate: {err}") from err

        result: dict[str, Any] = {
            "current_rate": round(current.rate, 5),
            "tier": current.tier,
            "season": current.season,
            "next_change": current.next_change.isoformat() if current.next_change else None,
            "utility_name": self._utility_name,
            "rate_plan_name": self._rate_plan_name,
            "last_api_fetch": self._last_api_fetch.isoformat() if self._last_api_fetch else None,
        }

        if self._configure_gas:
            result["gas_rate"] = self._gas_rate
            result["gas_unit"] = self._gas_unit

        return result

    async def _fetch_rate_schedule(self) -> None:
        """Fetch and parse the rate schedule from OpenEI."""
        _LOGGER.info(
            "Fetching rate schedule from OpenEI for %s - %s",
            self._utility_name, self._rate_plan_name,
        )

        client = self._get_client()
        raw_schedule = await client.get_rate_schedule(self._rate_plan_id)

        self._schedule = parse_openei_schedule(raw_schedule)
        self._calculator = RateCalculator(self._schedule)
        self._last_api_fetch = dt_util.now()

        _LOGGER.info(
            "Successfully fetched rate schedule. Seasons: %s",
            list(self._schedule.seasons.keys()),
        )
