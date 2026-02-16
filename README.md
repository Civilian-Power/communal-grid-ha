# Communal Grid - Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/Civilian-Power/communal-grid-ha)](https://github.com/Civilian-Power/communal-grid-ha/releases)

A Home Assistant custom integration that shows the current electricity and gas rate your home is paying. Fetches real rate schedule data from the [OpenEI Utility Rate Database](https://openei.org/wiki/Utility_Rate_Database), which covers 3,700+ US utilities.

## Features

- **Real-time electric rate** — Shows current $/kWh based on your Time-of-Use (TOU) schedule
- **Rate tier tracking** — Displays whether you're in peak, off-peak, partial-peak, or super off-peak
- **Automatic schedule updates** — Fetches rate data from OpenEI daily, recalculates every minute
- **Seasonal awareness** — Handles summer vs. winter rate differences automatically
- **Gas rate support** — Manually configure your gas rate ($/therm or $/ccf)
- **Automation-ready** — Use the Rate Tier sensor to trigger automations (e.g., turn off AC during peak)
- **HACS compatible** — Install through the Home Assistant Community Store

## Sensors

| Sensor | Example State | Unit | Description |
|--------|--------------|------|-------------|
| Electric Rate | `0.351` | $/kWh | Current electricity rate based on TOU schedule |
| Rate Tier | `peak` | — | Current tier: `peak`, `off_peak`, `partial_peak`, or `super_off_peak` |
| Gas Rate | `1.500` | $/therm | Static rate from your configuration |

## Prerequisites

1. **OpenEI API Key** (free) — Sign up at [apps.openei.org/services/api/signup](https://apps.openei.org/services/api/signup/)
2. **Know your rate plan** — Check your utility bill for the plan name (e.g., PG&E E-TOU-C)

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/Civilian-Power/communal-grid-ha` with category **Integration**
4. Search for **Communal Grid** and click **Download**
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/communal_grid/` folder to your Home Assistant's `custom_components/` directory
2. Restart Home Assistant

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Communal Grid**
3. Follow the 4-step setup:
   - **Step 1:** Enter your OpenEI API key
   - **Step 2:** Select your utility company from the dropdown
   - **Step 3:** Select your rate plan
   - **Step 4:** Optionally configure a gas rate

## Dashboard Cards

### Simple Entities Card

```yaml
type: entities
title: Communal Grid
show_header_toggle: false
entities:
  - entity: sensor.communal_grid_electric_rate
    name: Electric Rate
  - entity: sensor.communal_grid_rate_tier
    name: Current Tier
  - entity: sensor.communal_grid_gas_rate
    name: Gas Rate
```

### Color-Coded Rate Card (requires button-card from HACS)

```yaml
type: custom:button-card
entity: sensor.communal_grid_rate_tier
name: Electricity Rate
show_state: false
show_icon: true
icon: mdi:flash
custom_fields:
  rate: |
    [[[
      const rate = states['sensor.communal_grid_electric_rate'].state;
      return `$${Number(rate).toFixed(3)}/kWh`;
    ]]]
  tier: |
    [[[
      const tier = entity.state;
      const names = {
        'peak': 'Peak',
        'off_peak': 'Off-Peak',
        'partial_peak': 'Partial Peak',
        'super_off_peak': 'Super Off-Peak'
      };
      return names[tier] || tier;
    ]]]
styles:
  card:
    - border-radius: 16px
    - padding: 20px
    - background: |
        [[[
          const tier = entity.state;
          if (tier === 'peak') return 'linear-gradient(135deg, #ef4444, #dc2626)';
          if (tier === 'partial_peak') return 'linear-gradient(135deg, #f59e0b, #d97706)';
          if (tier === 'super_off_peak') return 'linear-gradient(135deg, #22c55e, #16a34a)';
          return 'linear-gradient(135deg, #3b82f6, #2563eb)';
        ]]]
    - color: white
  icon:
    - width: 32px
    - color: white
  name:
    - font-size: 14px
    - opacity: '0.9'
    - text-transform: uppercase
    - letter-spacing: 1px
  custom_fields:
    rate:
      - font-size: 32px
      - font-weight: bold
      - margin-top: 8px
    tier:
      - font-size: 16px
      - opacity: '0.9'
      - margin-top: 4px
```

### Rate History Graph

```yaml
type: history-graph
title: Rate History (24hr)
hours_to_show: 24
entities:
  - entity: sensor.communal_grid_electric_rate
    name: Electric Rate ($/kWh)
```

## Automation Examples

### Turn off AC during peak hours

```yaml
alias: 'Energy Saver: AC off during peak'
trigger:
  - platform: state
    entity_id: sensor.communal_grid_rate_tier
    to: 'peak'
action:
  - service: climate.set_hvac_mode
    target:
      entity_id: climate.living_room
    data:
      hvac_mode: 'off'
  - service: notify.mobile_app_your_phone
    data:
      title: 'Peak rates started'
      message: >
        Electric rate is now ${{ states('sensor.communal_grid_electric_rate') }}/kWh.
        AC has been turned off to save money.
```

### Start EV charging during off-peak

```yaml
alias: 'EV: Charge during off-peak'
trigger:
  - platform: state
    entity_id: sensor.communal_grid_rate_tier
    to: 'off_peak'
condition:
  - condition: state
    entity_id: binary_sensor.ev_charger_connected
    state: 'on'
action:
  - service: switch.turn_on
    target:
      entity_id: switch.ev_charger
```

## Updating Gas Rate

Go to **Settings → Devices & Services → Communal Grid → Configure** to update your gas rate at any time without reconfiguring the entire integration.

## Supported Utilities

Any US utility in the [OpenEI Utility Rate Database](https://apps.openei.org/USURDB/) is supported, including:

- Pacific Gas & Electric (PG&E)
- Southern California Edison (SCE)
- San Diego Gas & Electric (SDG&E)
- Los Angeles Dept. of Water & Power (LADWP)
- Duke Energy
- Florida Power & Light
- Commonwealth Edison (ComEd)
- And 3,700+ more...

## How It Works

1. During setup, the integration fetches your utility's rate schedule from OpenEI
2. Every 24 hours, it re-fetches the schedule to pick up any rate changes
3. Every 1 minute, it recalculates which TOU period is active based on:
   - Current time of day
   - Day of week (weekday vs. weekend)
   - Season (summer vs. winter)
4. Sensors update with the current rate and tier
5. If the API is unreachable, it continues using the last successfully fetched schedule

## Troubleshooting

- **"Invalid API key"** — Verify your key at [apps.openei.org](https://apps.openei.org). OpenEI keys are different from NREL developer keys.
- **No rate plans found** — Your utility may not have residential TOU plans in OpenEI. Try searching the [USRDB web interface](https://apps.openei.org/USURDB/) to verify.
- **Rate shows 0.0** — The rate plan may be flat-rate or tiered rather than TOU. Check the integration logs for parsing warnings.

## Contributing

Issues and pull requests welcome at [github.com/Civilian-Power/communal-grid-ha](https://github.com/Civilian-Power/communal-grid-ha).

## License

MIT
