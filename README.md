# Communal Grid - Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/Civilian-Power/communal-grid-ha)](https://github.com/Civilian-Power/communal-grid-ha/releases)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Civilian-Power&repository=communal-grid-ha&category=integration)

A Home Assistant custom integration that shows the current electricity and gas rate your home is paying, and discovers controllable devices that can help reduce your energy usage. Fetches real rate schedule data from the [OpenEI Utility Rate Database](https://openei.org/wiki/Utility_Rate_Database), which covers 3,700+ US utilities.

## Features

- **Real-time electric rate** — Shows current $/kWh based on your Time-of-Use (TOU) schedule
- **Rate tier tracking** — Displays whether you're in peak, off-peak, partial-peak, or super off-peak
- **Automatic schedule updates** — Fetches rate data from OpenEI daily, recalculates every minute
- **Seasonal awareness** — Handles summer vs. winter rate differences automatically
- **Gas rate support** — Manually configure your gas rate ($/therm or $/ccf)
- **Device discovery** — Automatically finds thermostats, smart plugs, EV chargers, water heaters, smart lights, and power monitors in your Home Assistant
- **Power consumption tracking** — Shows current watts and estimated annual kWh for devices that report power usage (e.g., TP-Link KP115)
- **VPP program directory** — Bundled registry of 10+ Virtual Power Plant programs with enrollment links and reward info
- **DER device mapping** — Maps your discovered devices to Distributed Energy Resource types for VPP eligibility
- **Automation-ready** — Use the Rate Tier sensor to trigger automations (e.g., turn off AC during peak)
- **HACS compatible** — Install through the Home Assistant Community Store

## Sensors

| Sensor | Example State | Unit | Description |
|--------|--------------|------|-------------|
| Electric Rate | `0.351` | $/kWh | Current electricity rate based on TOU schedule |
| Rate Tier | `peak` | — | Current tier: `peak`, `off_peak`, `partial_peak`, or `super_off_peak` |
| Gas Rate | `1.500` | $/therm | Static rate from your configuration |
| Controllable Devices | `7` | devices | Count of energy-relevant devices discovered in HA |
| VPP Matches | `3` | programs | Count of VPP programs matching your utility and devices |

The **Controllable Devices** sensor includes detailed attributes: per-category counts, device names, manufacturers, models, current power draw (watts), and estimated annual energy usage (kWh/year) for devices with power monitoring.

The **VPP Matches** sensor cross-references your configured utility and discovered devices against the VPP registry using model-specific matching. Its attributes include each matching VPP's name, reward info, enrollment link, and a list of your qualifying devices with their power data.

## Prerequisites

1. **OpenEI API Key** (free) — Sign up at [apps.openei.org/services/api/signup](https://apps.openei.org/services/api/signup/)
2. **Know your rate plan** — Check your utility bill for the plan name (e.g., PG&E E-TOU-C)

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Civilian-Power&repository=communal-grid-ha&category=integration)

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
   - **Step 2:** Select your utility company — the list is automatically filtered to utilities near your Home Assistant home location
   - **Step 3:** Select your rate plan
   - **Step 4:** Optionally configure a gas rate

> **Note:** The utility auto-detection uses the home location configured in **Settings → System → General**. Make sure your home address is set for the best results.

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
  - entity: sensor.communal_grid_controllable_devices
    name: Controllable Devices
  - entity: sensor.communal_grid_vpp_matches
    name: VPP Matches
  - entity: sensor.communal_grid_gas_rate
    name: Gas Rate
```

### Color-Coded Rate Card (requires button-card from HACS)

```yaml
type: custom:button-card
entity: sensor.communal_grid_rate_tier
layout: vertical
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
  grid:
    - grid-template-areas: '"i" "n" "rate" "tier"'
    - grid-template-rows: auto auto auto auto
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

### Controllable Devices Card with Power Usage (requires button-card from HACS)

Shows all discovered devices grouped by category, with current power draw and estimated annual kWh for devices that report usage.

```yaml
type: vertical-stack
cards:
  - type: custom:button-card
    entity: sensor.communal_grid_controllable_devices
    layout: vertical
    name: Controllable Devices
    show_state: false
    show_icon: true
    icon: mdi:devices
    custom_fields:
      count: |
        [[[
          const total = entity.state;
          const power = entity.attributes.total_current_power_w;
          let text = `${total} devices found`;
          if (power > 0) text += ` · ${power.toFixed(0)} W now`;
          return text;
        ]]]
      annual: |
        [[[
          const annual = entity.attributes.total_estimated_annual_kwh;
          const monitored = entity.attributes.monitored_device_count;
          if (annual > 0) return `~${annual.toFixed(0)} kWh/yr estimated (${monitored} monitored)`;
          return '';
        ]]]
    styles:
      grid:
        - grid-template-areas: '"i" "n" "count" "annual"'
        - grid-template-rows: auto auto auto auto
      card:
        - border-radius: 16px 16px 0 0
        - padding: 20px
        - background: 'linear-gradient(135deg, #6366f1, #4f46e5)'
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
        count:
          - font-size: 24px
          - font-weight: bold
          - margin-top: 8px
        annual:
          - font-size: 13px
          - opacity: '0.8'
          - margin-top: 4px
  - type: markdown
    content: >
      {% set s = states.sensor.communal_grid_controllable_devices %}
      {% if s and s.attributes %}

      {% set thermostats = s.attributes.get('thermostats', []) %}
      {% set plugs = s.attributes.get('smart_plugs', []) %}
      {% set evs = s.attributes.get('ev_chargers', []) %}
      {% set heaters = s.attributes.get('water_heaters', []) %}
      {% set lights = s.attributes.get('smart_lights', []) %}
      {% set monitors = s.attributes.get('power_monitors', []) %}

      {% macro device_line(d) %}
      - **{{ d.name }}**{% if d.manufacturer %} · {{ d.manufacturer }}{% endif %}{% if d.model %} {{ d.model }}{% endif %}{% if d.current_power_w != None %} · ⚡ {{ d.current_power_w }}W (est. {{ d.estimated_annual_kwh }} kWh/yr){% endif %}

      {% endmacro %}

      {% if thermostats | length > 0 %}

      **🌡️ Thermostats ({{ thermostats | length }})**

      {% for d in thermostats %}{{ device_line(d) }}{% endfor %}{% endif %}

      {% if plugs | length > 0 %}

      **🔌 Smart Plugs ({{ plugs | length }})**

      {% for d in plugs %}{{ device_line(d) }}{% endfor %}{% endif %}

      {% if evs | length > 0 %}

      **🚗 EV Chargers ({{ evs | length }})**

      {% for d in evs %}{{ device_line(d) }}{% endfor %}{% endif %}

      {% if heaters | length > 0 %}

      **🔥 Water Heaters ({{ heaters | length }})**

      {% for d in heaters %}{{ device_line(d) }}{% endfor %}{% endif %}

      {% if lights | length > 0 %}

      **💡 Smart Lights ({{ lights | length }})**

      {% for d in lights %}{{ device_line(d) }}{% endfor %}{% endif %}

      {% if monitors | length > 0 %}

      **⚡ Power Monitors ({{ monitors | length }})**

      {% for d in monitors %}{{ device_line(d) }}{% endfor %}{% endif %}

      {% else %}
      No device data available yet.
      {% endif %}
```

### VPP Matches Card (requires button-card from HACS)

Shows which Virtual Power Plant programs are available in your region for your specific devices, with per-VPP qualifying device lists, power usage, and enrollment links.

```yaml
type: vertical-stack
cards:
  - type: custom:button-card
    entity: sensor.communal_grid_vpp_matches
    layout: vertical
    name: VPP Programs
    show_state: false
    show_icon: true
    icon: mdi:lightning-bolt-circle
    custom_fields:
      count: |
        [[[
          const n = entity.state;
          if (n == 0) return 'No matching programs found';
          return `${n} program${n > 1 ? 's' : ''} match your devices`;
        ]]]
      utility: |
        [[[
          const u = entity.attributes.utility_name || '';
          return u ? `Utility: ${u}` : '';
        ]]]
    styles:
      grid:
        - grid-template-areas: '"i" "n" "count" "utility"'
        - grid-template-rows: auto auto auto auto
      card:
        - border-radius: 16px 16px 0 0
        - padding: 20px
        - background: 'linear-gradient(135deg, #059669, #047857)'
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
        count:
          - font-size: 24px
          - font-weight: bold
          - margin-top: 8px
        utility:
          - font-size: 13px
          - opacity: '0.8'
          - margin-top: 4px
  - type: markdown
    content: |
      {% set s = states.sensor.communal_grid_vpp_matches %}
      {% if s and s.attributes and s.attributes.matching_vpps is defined %}
      {% set vpps = s.attributes.matching_vpps %}
      {% if vpps | length == 0 %}
      *No VPP programs match your current utility and devices. Add more smart devices or check back as new programs launch.*
      {% else %}
      {% for vpp in vpps %}
      ---
      ### ⚡ {{ vpp.name }}
      **{{ vpp.provider }}** · {{ vpp.matching_device_count }} qualifying device{{ 's' if vpp.matching_device_count != 1 }}
      {% if vpp.reward and vpp.reward.description %}
      💰 {{ vpp.reward.description }}
      {% endif %}
      {% for d in vpp.matching_devices %}
      - **{{ d.name }}**{% if d.manufacturer %} · {{ d.manufacturer }}{% endif %}{% if d.model %} {{ d.model }}{% endif %}{% if d.current_power_w %} · ⚡ {{ d.current_power_w | round(0) }}W{% endif %}{% if d.estimated_annual_kwh %} ({{ d.estimated_annual_kwh | round(0) }} kWh/yr){% endif %}
      {% endfor %}
      {% if vpp.total_matching_annual_kwh > 0 %}
      **Total:** {{ vpp.total_matching_power_w | round(0) }}W now · ~{{ vpp.total_matching_annual_kwh | round(0) }} kWh/yr
      {% endif %}
      {% if vpp.enrollment_url %}
      <a href="{{ vpp.enrollment_url }}" target="_blank" style="display:inline-block;padding:8px 20px;background:#059669;color:white;border-radius:8px;text-decoration:none;font-weight:bold;font-size:14px;">Enroll →</a>
      {% endif %}
      {% endfor %}
      {% endif %}
      {% else %}
      *VPP matching data not available yet. Waiting for device discovery...*
      {% endif %}
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

1. During setup, the integration uses your Home Assistant home location to find nearby utilities, then fetches your selected utility's rate schedule from OpenEI
2. Every 24 hours, it re-fetches the schedule to pick up any rate changes
3. Every 1 minute, it recalculates which TOU period is active based on:
   - Current time of day
   - Day of week (weekday vs. weekend)
   - Season (summer vs. winter)
4. Every 5 minutes, it scans your Home Assistant for controllable energy devices and reads their current power draw
5. Sensors update with the current rate, tier, and device information
6. If the API is unreachable, it continues using the last successfully fetched schedule

## Device Discovery

Communal Grid automatically discovers devices across your Home Assistant that can help reduce energy usage. It scans the entity and device registries every 5 minutes and categorizes devices into:

| Category | What it finds | How it detects them |
|----------|--------------|---------------------|
| Thermostats | Nest, Ecobee, etc. | All `climate` domain entities |
| Smart Plugs | TP-Link, Kasa, Shelly, Meross, etc. | `switch` entities with `device_class: outlet` or known manufacturers |
| EV Chargers | Wallbox, ChargePoint, OpenEVSE, etc. | Keyword matching on entity name/model |
| Water Heaters | Any smart water heater | All `water_heater` domain entities |
| Smart Lights | Any smart light | All `light` domain entities |
| Power Monitors | Energy monitoring sensors | `sensor` entities with `device_class: power` or `energy` |

For devices with power monitoring (like the TP-Link KP115), Communal Grid reads the current wattage and estimates annual energy usage based on `watts × 8,760 hours ÷ 1,000`.

## VPP & DER Registries

Communal Grid includes two bundled data registries that map your discovered devices to real-world energy programs:

### Virtual Power Plants (VPPs)

The **VPP registry** (`data/vpp_registry.json`) is a curated list of Virtual Power Plant programs across the US. Each entry includes:

| Field | Description |
|-------|-------------|
| Geographic regions | States and specific utilities the program serves |
| Enrollment URL | Where to sign up for the program |
| Management URL | Where to manage your enrollment |
| Supported devices | **Model-specific** — which manufacturer/model combos the program works with |
| Reward structure | How you get paid — per kWh, per event, flat monthly/yearly |

VPP device compatibility is at the **manufacturer + model** level, not just device category. For example, OhmConnect supports TP-Link KP115 (energy monitoring) but not KP125M. Each `supported_devices` entry specifies the DER type, manufacturer, and models with three match modes: exact match (default), prefix match (for model families like "EcoNet*"), or wildcard (`"*"` for any).

**Included VPP programs:** OhmConnect, Tesla Virtual Power Plant, Nest Renew, Enphase VPP, sonnenCommunity, Sunrun VPP, Generac Concerto, Enel X Demand Response, Virtual Peaker BYOD, Swell Energy VPP.

### Distributed Energy Resources (DERs)

The **DER registry** (`data/der_registry.json`) maps device types to your Home Assistant devices and to VPP programs. Each entry includes:

| Field | Description |
|-------|-------------|
| HA domain & category | Maps to your Controllable Devices sensor categories |
| Controllable actions | What actions can be automated (e.g., set_temperature, turn_off) |
| Energy impact | Low, medium, high, or very high |
| Typical power range | Min/max watts for the device type |
| VPP compatible | Whether VPP programs support this device type |
| Demand response role | How this device helps during grid events |

**Included DER types:** Smart Thermostat, Smart Plug, EV Charger, Smart Water Heater, Smart Light, Home Battery, Pool Pump, Solar Inverter.

### How They Connect

```
Your HA Devices              DER Type              VPP Match (model-specific)
───────────────────────   ─────────────────   ─────────────────────────────
Google Nest Thermostat ──► smart_thermostat ──► OhmConnect (Nest models ✓)
                                            ──► Nest Renew (Nest models ✓)
                                            ──► Enel X (any thermostat ✓)

TP-Link KP115          ──► smart_plug      ──► OhmConnect (KP115 ✓)
                                            ──► Enel X (any plug ✓)

TP-Link KP125M         ──► smart_plug      ──► OhmConnect (KP125M ✗)
                                            ──► Enel X (any plug ✓)

Rheem EcoNet WH        ──► smart_water_htr ──► OhmConnect (EcoNet* ✓)
Rheem Performance WH   ──► smart_water_htr ──► OhmConnect (not EcoNet ✗)

Tesla Powerwall 3      ──► battery_storage ──► Tesla VPP (Powerwall* ✓)
                                            ──► Swell Energy (Powerwall* ✓)
```

### Updating the Registries

Both registry files are standalone JSON and can be updated without changing any code:

1. Edit `custom_components/communal_grid/data/vpp_registry.json` to add/remove VPP programs
2. Edit `custom_components/communal_grid/data/der_registry.json` to add/remove DER device types
3. Restart Home Assistant to reload the updated data

## Troubleshooting

- **"Invalid API key"** — Verify your key at [apps.openei.org](https://apps.openei.org). OpenEI keys are different from NREL developer keys.
- **No rate plans found** — Your utility may not have residential TOU plans in OpenEI. Try searching the [USRDB web interface](https://apps.openei.org/USURDB/) to verify.
- **Rate shows 0.0** — The rate plan may be flat-rate or tiered rather than TOU. Check the integration logs for parsing warnings.
- **Controllable Devices shows 0** — Make sure your other integrations (Nest, TP-Link, etc.) are set up and working in Home Assistant first. Communal Grid can only discover devices that are already registered.

## Contributing

Issues and pull requests welcome at [github.com/Civilian-Power/communal-grid-ha](https://github.com/Civilian-Power/communal-grid-ha).

## License

MIT
