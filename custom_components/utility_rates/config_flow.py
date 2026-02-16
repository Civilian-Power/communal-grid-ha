"""Config flow for Utility Rates integration.

Walks the user through 4 steps:
1. Enter OpenEI API key
2. Select their utility company
3. Select their rate plan
4. Optionally configure gas rate
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_UTILITY_ID,
    CONF_UTILITY_NAME,
    CONF_RATE_PLAN_ID,
    CONF_RATE_PLAN_NAME,
    CONF_CONFIGURE_GAS,
    CONF_GAS_RATE,
    CONF_GAS_UNIT,
    DEFAULT_GAS_RATE,
    DEFAULT_GAS_UNIT,
    GAS_UNITS,
)
from .openei_client import OpenEIClient, OpenEIAuthError, OpenEIConnectionError, OpenEIError

_LOGGER = logging.getLogger(__name__)


class UtilityRatesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Utility Rates."""

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

            # Validate the API key
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
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                }
            ),
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

            # Find the matching utility
            for utility in self._utilities:
                if utility["utility_id"] == selected:
                    self._data[CONF_UTILITY_ID] = utility["utility_id"]
                    self._data[CONF_UTILITY_NAME] = utility["name"]
                    return await self.async_step_select_rate_plan()

            errors["base"] = "invalid_utility"

        # Fetch utilities list
        if not self._utilities:
            try:
                session = async_get_clientsession(self.hass)
                client = OpenEIClient(session, self._data[CONF_API_KEY])
                self._utilities = await client.get_utilities()
            except OpenEIError as err:
                _LOGGER.error("Failed to fetch utilities: %s", err)
                return self.async_abort(reason="api_error")

        if not self._utilities:
            return self.async_abort(reason="no_utilities")

        # Build dropdown options: {utility_id: display_name}
        utility_options = {
            u["utility_id"]: u["name"] for u in self._utilities
        }

        return self.async_show_form(
            step_id="select_utility",
            data_schema=vol.Schema(
                {
                    vol.Required("utility_selection"): vol.In(utility_options),
                }
            ),
            errors=errors,
        )

    async def async_step_select_rate_plan(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Select rate plan."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected = user_input.get("rate_plan_selection", "")

            # Find the matching plan
            for plan in self._rate_plans:
                if plan["label"] == selected:
                    self._data[CONF_RATE_PLAN_ID] = plan["label"]
                    self._data[CONF_RATE_PLAN_NAME] = plan["name"]
                    return await self.async_step_gas_config()

            errors["base"] = "invalid_rate_plan"

        # Fetch rate plans for the selected utility
        if not self._rate_plans:
            try:
                session = async_get_clientsession(self.hass)
                client = OpenEIClient(session, self._data[CONF_API_KEY])
                self._rate_plans = await client.get_rate_plans(
                    self._data[CONF_UTILITY_ID]
                )
            except OpenEIError as err:
                _LOGGER.error("Failed to fetch rate plans: %s", err)
                return self.async_abort(reason="api_error")

        if not self._rate_plans:
            return self.async_abort(reason="no_rate_plans")

        # Build dropdown options
        plan_options = {
            p["label"]: f"{p['name']}" + (
                f" ({p['effective_date']})" if p.get("effective_date") else ""
            )
            for p in self._rate_plans
        }

        return self.async_show_form(
            step_id="select_rate_plan",
            data_schema=vol.Schema(
                {
                    vol.Required("rate_plan_selection"): vol.In(plan_options),
                }
            ),
            errors=errors,
        )

    async def async_step_gas_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 4: Optionally configure gas rate."""
        if user_input is not None:
            self._data[CONF_CONFIGURE_GAS] = user_input.get(CONF_CONFIGURE_GAS, False)

            if self._data[CONF_CONFIGURE_GAS]:
                self._data[CONF_GAS_RATE] = user_input.get(CONF_GAS_RATE, DEFAULT_GAS_RATE)
                self._data[CONF_GAS_UNIT] = user_input.get(CONF_GAS_UNIT, DEFAULT_GAS_UNIT)

            # Create the config entry
            title = f"{self._data[CONF_UTILITY_NAME]} - {self._data[CONF_RATE_PLAN_NAME]}"
            return self.async_create_entry(title=title, data=self._data)

        return self.async_show_form(
            step_id="gas_config",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CONFIGURE_GAS, default=False): bool,
                    vol.Optional(CONF_GAS_RATE, default=DEFAULT_GAS_RATE): vol.Coerce(float),
                    vol.Optional(CONF_GAS_UNIT, default=DEFAULT_GAS_UNIT): vol.In(
                        {k: v for k, v in GAS_UNITS.items()}
                    ),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> UtilityRatesOptionsFlow:
        """Get the options flow handler."""
        return UtilityRatesOptionsFlow(config_entry)


class UtilityRatesOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for updating gas rate without full reconfiguration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options step."""
        if user_input is not None:
            # Update the config entry data with new gas settings
            new_data = {**self._config_entry.data}
            new_data[CONF_CONFIGURE_GAS] = user_input.get(CONF_CONFIGURE_GAS, False)
            new_data[CONF_GAS_RATE] = user_input.get(CONF_GAS_RATE, DEFAULT_GAS_RATE)
            new_data[CONF_GAS_UNIT] = user_input.get(CONF_GAS_UNIT, DEFAULT_GAS_UNIT)

            self.hass.config_entries.async_update_entry(
                self._config_entry, data=new_data
            )
            return self.async_create_entry(title="", data={})

        current_data = self._config_entry.data

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CONFIGURE_GAS,
                        default=current_data.get(CONF_CONFIGURE_GAS, False),
                    ): bool,
                    vol.Optional(
                        CONF_GAS_RATE,
                        default=current_data.get(CONF_GAS_RATE, DEFAULT_GAS_RATE),
                    ): vol.Coerce(float),
                    vol.Optional(
                        CONF_GAS_UNIT,
                        default=current_data.get(CONF_GAS_UNIT, DEFAULT_GAS_UNIT),
                    ): vol.In({k: v for k, v in GAS_UNITS.items()}),
                }
            ),
        )
