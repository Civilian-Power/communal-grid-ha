"""Constants for the Communal Grid integration."""
from datetime import timedelta

DOMAIN = "communal_grid"
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

# Device discovery
DEVICE_DISCOVERY_INTERVAL = timedelta(minutes=5)
SENSOR_CONTROLLABLE_DEVICES = "controllable_devices"

# Device categories
DEVICE_CAT_THERMOSTAT = "thermostat"
DEVICE_CAT_SMART_PLUG = "smart_plug"
DEVICE_CAT_EV_CHARGER = "ev_charger"
DEVICE_CAT_WATER_HEATER = "water_heater"
DEVICE_CAT_SMART_LIGHT = "smart_light"
DEVICE_CAT_POWER_MONITOR = "power_monitor"

# Known smart plug manufacturers (case-insensitive matching)
SMART_PLUG_MANUFACTURERS = [
    "tp-link",
    "kasa",
    "shelly",
    "lutron",
    "wemo",
    "meross",
    "sonoff",
    "tuya",
    "tasmota",
    "gosund",
    "teckin",
]

# Keywords that indicate an EV charger (matched against entity name/model, case-insensitive)
EV_CHARGER_KEYWORDS = [
    "ev_charger",
    "ev charger",
    "evse",
    "wallbox",
    "chargepoint",
    "juicebox",
    "grizzl-e",
    "openevse",
    "emporia",
    "tesla wall connector",
    "peblar",
    "keba",
]

# Energy impact levels (used by DER registry)
ENERGY_IMPACT_LOW = "low"
ENERGY_IMPACT_MEDIUM = "medium"
ENERGY_IMPACT_HIGH = "high"
ENERGY_IMPACT_VERY_HIGH = "very_high"

# VPP reward types
VPP_REWARD_PER_KWH = "per_kwh"
VPP_REWARD_PER_EVENT = "per_event"
VPP_REWARD_FLAT_MONTHLY = "flat_monthly"
VPP_REWARD_FLAT_YEARLY = "flat_yearly"
