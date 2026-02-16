"""OpenEI USRDB API client for fetching utility rate data."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import OPENEI_BASE_URL, OPENEI_API_TIMEOUT, OPENEI_MAX_RETRIES

_LOGGER = logging.getLogger(__name__)


class OpenEIError(Exception):
    """Base exception for OpenEI API errors."""


class OpenEIAuthError(OpenEIError):
    """Authentication error (invalid API key)."""


class OpenEIConnectionError(OpenEIError):
    """Connection error (network issues)."""


class OpenEIClient:
    """Client for the OpenEI Utility Rate Database API."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        """Initialize the OpenEI client.

        Args:
            session: aiohttp client session (provided by Home Assistant).
            api_key: OpenEI API key from apps.openei.org.
        """
        self._session = session
        self._api_key = api_key

    async def _api_request(
        self, params: dict[str, Any], retries: int = OPENEI_MAX_RETRIES
    ) -> dict[str, Any]:
        """Make an API request to OpenEI with retry logic.

        Args:
            params: Query parameters for the API call.
            retries: Number of retry attempts remaining.

        Returns:
            Parsed JSON response dictionary.

        Raises:
            OpenEIAuthError: If the API key is invalid.
            OpenEIConnectionError: If the request fails after all retries.
        """
        # Always include these base params
        params.update({
            "version": "latest",
            "format": "json",
            "api_key": self._api_key,
        })

        for attempt in range(retries):
            try:
                _LOGGER.debug(
                    "OpenEI API request (attempt %d/%d): %s",
                    attempt + 1,
                    retries,
                    {k: v for k, v in params.items() if k != "api_key"},
                )

                async with self._session.get(
                    OPENEI_BASE_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=OPENEI_API_TIMEOUT),
                ) as response:
                    if response.status == 401:
                        raise OpenEIAuthError(
                            "Invalid OpenEI API key. Get a free key at "
                            "https://apps.openei.org/services/api/signup/"
                        )

                    if response.status == 429:
                        wait_time = 2 ** (attempt + 1)
                        _LOGGER.warning(
                            "OpenEI rate limit hit, waiting %ds before retry",
                            wait_time,
                        )
                        await asyncio.sleep(wait_time)
                        continue

                    if response.status != 200:
                        text = await response.text()
                        raise OpenEIConnectionError(
                            f"OpenEI API returned status {response.status}: {text[:200]}"
                        )

                    data = await response.json()

                    # Check for API-level errors in response body
                    if isinstance(data, dict) and "error" in data:
                        error_msg = data["error"]
                        if "api_key" in str(error_msg).lower():
                            raise OpenEIAuthError(str(error_msg))
                        raise OpenEIError(str(error_msg))

                    return data

            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                if attempt < retries - 1:
                    wait_time = 2 ** (attempt + 1)
                    _LOGGER.warning(
                        "OpenEI request failed (%s), retrying in %ds",
                        str(err),
                        wait_time,
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise OpenEIConnectionError(
                        f"Failed to connect to OpenEI after {retries} attempts: {err}"
                    ) from err

        raise OpenEIConnectionError("Exhausted all retry attempts")

    async def validate_api_key(self) -> bool:
        """Test if the API key is valid by making a minimal request.

        Returns:
            True if the key is valid.

        Raises:
            OpenEIAuthError: If the key is invalid.
            OpenEIConnectionError: If the connection fails.
        """
        try:
            await self._api_request({
                "limit": "1",
                "detail": "minimal",
            })
            return True
        except OpenEIAuthError:
            raise
        except OpenEIError as err:
            _LOGGER.error("API key validation failed: %s", err)
            raise

    async def get_utilities(self, state: str | None = None) -> list[dict[str, str]]:
        """Get a list of available utilities.

        Args:
            state: Optional US state abbreviation to filter (e.g., "CA").

        Returns:
            List of dicts with 'name' and 'utility_id' keys.
        """
        params: dict[str, Any] = {
            "detail": "minimal",
            "limit": "500",
            "sector": "Residential",
        }

        if state:
            params["address"] = state

        data = await self._api_request(params)
        items = data.get("items", [])

        # Extract unique utilities from the rate entries
        utilities: dict[str, str] = {}
        for item in items:
            utility_name = item.get("utility", "")
            eia_id = item.get("eiaid", "")
            if utility_name and eia_id and utility_name not in utilities:
                utilities[utility_name] = str(eia_id)

        # Sort alphabetically by name
        result = [
            {"name": name, "utility_id": uid}
            for name, uid in sorted(utilities.items())
        ]

        _LOGGER.debug("Found %d utilities", len(result))
        return result

    async def get_rate_plans(self, utility_id: str) -> list[dict[str, Any]]:
        """Get available rate plans for a specific utility.

        Args:
            utility_id: The EIA ID of the utility.

        Returns:
            List of rate plan dicts with name, label, plan_id, etc.
        """
        params: dict[str, Any] = {
            "eia": utility_id,
            "sector": "Residential",
            "detail": "minimal",
            "limit": "100",
            "orderby": "startdate",
            "direction": "desc",
        }

        data = await self._api_request(params)
        items = data.get("items", [])

        plans = []
        seen_labels = set()
        for item in items:
            label = item.get("name", "") or item.get("label", "")
            plan_id = item.get("label", "")

            if not label or label in seen_labels:
                continue
            seen_labels.add(label)

            plans.append({
                "name": label,
                "label": plan_id,
                "description": item.get("description", ""),
                "effective_date": item.get("startdate", ""),
                "end_date": item.get("enddate", ""),
                "source": item.get("source", ""),
                "uri": item.get("uri", ""),
            })

        _LOGGER.debug("Found %d rate plans for utility %s", len(plans), utility_id)
        return plans

    async def get_rate_schedule(self, rate_label: str) -> dict[str, Any]:
        """Fetch the full rate schedule for a specific rate plan.

        This is the main data fetch — returns the complete TOU structure
        including seasonal rates, peak/off-peak periods, and pricing.

        Args:
            rate_label: The rate plan label/URI from OpenEI.

        Returns:
            Full rate schedule dictionary from OpenEI.
        """
        params: dict[str, Any] = {
            "getpage": rate_label,
            "detail": "full",
        }

        data = await self._api_request(params)
        items = data.get("items", [])

        if not items:
            raise OpenEIError(
                f"No rate schedule found for plan '{rate_label}'. "
                "The rate plan may have been retired or the ID is incorrect."
            )

        schedule = items[0]
        _LOGGER.debug(
            "Fetched rate schedule: %s (utility: %s)",
            schedule.get("name", "unknown"),
            schedule.get("utility", "unknown"),
        )

        return schedule
