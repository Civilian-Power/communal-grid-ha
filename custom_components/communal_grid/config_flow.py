"""Config flow for Communal Grid integration.

Walks the user through 3 steps:
1. Enter OpenEI API key
2. Select their utility company (auto-detected from HA home location)
3. Select their rate plan
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_UTILITY_ID,
    CONF_UTILITY_NAME,
    CONF_RATE_PLAN_ID,
    CONF_RATE_PLAN_NAME,
)
from .openei_client import OpenEIClient, OpenEIAuthError, OpenEIConnectionError, OpenEIError

_LOGGER = logging.getLogger(__name__)


class CommunalGridConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Communal Grid."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._data: dict[str, Any] = {}
        self._utilities: list[dict[str, str]] = []
        self._rate_plans: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Enter OpenEI API key."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()

            try:
                session = async_get_clientsession(self.hass)
                client = OpenEIClient(session, api_key)
                await client.validate_api_key()
            except OpenEIAuthError:
                errors["base"] = "invalid_api_key"
            except OpenEIConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error validating API key")
                errors["base"] = "unknown"

            if not errors:
                self._data[CONF_API_KEY] = api_key
                return await self.async_step_select_utility()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }),
            errors=errors,
            description_placeholders={
                "signup_url": "https://apps.openei.org/services/api/signup/"
            },
        )

    async def async_step_select_utility(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Select utility company."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected = user_input.get("utility_selection", "")
            for utility in self._utilities:
                if utility["utility_id"] == selected:
                    self._data[CONF_UTILITY_ID] = utility["utility_id"]
                    self._data[CONF_UTILITY_NAME] = utility["name"]
                    return await self.async_step_select_rate_plan()
            errors["base"] = "invalid_utility"

        if not self._utilities:
            try:
                session = async_get_clientsession(self.hass)
                client = OpenEIClient(session, self._data[CONF_API_KEY])

                # Use Home Assistant's configured home location to find nearby utilities
                lat = self.hass.config.latitude
                lon = self.hass.config.longitude

                if lat and lon:
                    _LOGGER.debug(
                        "Using HA home location (%.4f, %.4f) to find utilities", lat, lon
                    )
                    self._utilities = await client.get_utilities(lat=lat, lon=lon)
                else:
                    _LOGGER.debug("No home location set, fetching all utilities")
                    self._utilities = await client.get_utilities()
            except OpenEIError as err:
                _LOGGER.error("Failed to fetch utilities: %s", err)
                return self.async_abort(reason="api_error")

        if not self._utilities:
            return self.async_abort(reason="no_utilities")

        utility_options = {u["utility_id"]: u["name"] for u in self._utilities}

        return self.async_show_form(
            step_id="select_utility",
            data_schema=vol.Schema({vol.Required("utility_selection"): vol.In(utility_options)}),
            errors=errors,
        )

    async def async_step_select_rate_plan(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Select rate plan."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected = user_input.get("rate_plan_selection", "")
            for plan in self._rate_plans:
                if plan["label"] == selected:
                    self._data[CONF_RATE_PLAN_ID] = plan["label"]
                    self._data[CONF_RATE_PLAN_NAME] = plan["name"]
                    title = f"{self._data[CONF_UTILITY_NAME]} - {self._data[CONF_RATE_PLAN_NAME]}"
                    return self.async_create_entry(title=title, data=self._data)
            errors["base"] = "invalid_rate_plan"

        if not self._rate_plans:
            try:
                session = async_get_clientsession(self.hass)
                client = OpenEIClient(session, self._data[CONF_API_KEY])
                self._rate_plans = await client.get_rate_plans(self._data[CONF_UTILITY_ID])
            except OpenEIError as err:
                _LOGGER.error("Failed to fetch rate plans: %s", err)
                return self.async_abort(reason="api_error")

        if not self._rate_plans:
            return self.async_abort(reason="no_rate_plans")

        plan_options = {
            p["label"]: f"{p['name']}" + (f" ({p['effective_date']})" if p.get("effective_date") else "")
            for p in self._rate_plans
        }

        return self.async_show_form(
            step_id="select_rate_plan",
            data_schema=vol.Schema({vol.Required("rate_plan_selection"): vol.In(plan_options)}),
            errors=errors,
        )

