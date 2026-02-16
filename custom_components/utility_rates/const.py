"""Constants for the Communal Grid integration."""
from datetime import timedelta

DOMAIN = "utility_rates"
PLATFORMS = ["sensor"]

# Update intervals
UPDATE_INTERVAL = timedelta(minutes=1)  # Recalculate current rate every minute
API_FETCH_INTERVAL = timedelta(hours=24)  # Fetch fresh rates from OpenEI daily

# OpenEI API
OPENEI_BASE_URL = "https://api.openei.org/utility_rates"
OPENEI_API_TIMEOUT = 15  # seconds
OPENEI_MAX_RETRIES = 3

# Configuration keys
CONF_API_KEY = "api_key"
CONF_UTILITY_ID = "utility_id"
CONF_UTILITY_NAME = "utility_name"
CONF_RATE_PLAN_ID = "rate_plan_id"
CONF_RATE_PLAN_NAME = "rate_plan_name"
CONF_CONFIGURE_GAS = "configure_gas"
CONF_GAS_RATE = "gas_rate"
CONF_GAS_UNIT = "gas_unit"

# Defaults
DEFAULT_GAS_RATE = 1.50
DEFAULT_GAS_UNIT = "therm"

# Rate tiers
TIER_PEAK = "peak"
TIER_OFF_PEAK = "off_peak"
TIER_PARTIAL_PEAK = "partial_peak"
TIER_SUPER_OFF_PEAK = "super_off_peak"

# Seasons
SEASON_SUMMER = "summer"
SEASON_WINTER = "winter"

# Summer is June 1 - September 30 for most CA utilities
SUMMER_START_MONTH = 6
SUMMER_END_MONTH = 9

# Sensor types
SENSOR_ELECTRIC_RATE = "electric_rate"
SENSOR_RATE_TIER = "rate_tier"
SENSOR_GAS_RATE = "gas_rate"

# Gas unit options
GAS_UNITS = {
    "therm": "$/therm",
    "ccf": "$/ccf",
}
