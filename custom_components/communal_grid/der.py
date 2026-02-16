"""Distributed Energy Resource (DER) registry loader and query helpers.

Loads the DER registry from the bundled JSON data file and provides
methods to map DER types to Home Assistant device categories (from the
Controllable Devices sensor) and to VPP programs.

The JSON file (data/der_registry.json) can be updated independently
of the integration code — just edit the file and restart HA.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Path to the bundled DER registry data file
_DATA_DIR = Path(__file__).parent / "data"
_DER_REGISTRY_FILE = _DATA_DIR / "der_registry.json"


@dataclass
class DERTypicalPower:
    """Typical power range for a DER device type."""

    min_w: int
    max_w: int

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary."""
        return {"min_w": self.min_w, "max_w": self.max_w}


@dataclass
class DEREntry:
    """A Distributed Energy Resource type entry.

    Maps a DER type (e.g., "smart_thermostat") to HA entity domains
    and device categories used by the Controllable Devices sensor.
    """

    id: str
    name: str
    description: str
    ha_domain: str  # HA entity domain (e.g., "climate", "switch", "light")
    ha_device_category: str  # Maps to DEVICE_CAT_* from const.py
    controllable_actions: list[str]
    energy_impact: str  # "low", "medium", "high", "very_high"
    typical_power: DERTypicalPower | None
    common_manufacturers: list[str]
    vpp_compatible: bool
    demand_response_role: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for sensor attributes."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "ha_domain": self.ha_domain,
            "ha_device_category": self.ha_device_category,
            "controllable_actions": self.controllable_actions,
            "energy_impact": self.energy_impact,
            "typical_power": self.typical_power.to_dict() if self.typical_power else None,
            "common_manufacturers": self.common_manufacturers,
            "vpp_compatible": self.vpp_compatible,
            "demand_response_role": self.demand_response_role,
        }

    def matches_ha_category(self, ha_category: str) -> bool:
        """Check if this DER type maps to a given HA device category.

        Args:
            ha_category: Device category from the Controllable Devices sensor
                         (e.g., "thermostat", "smart_plug", "ev_charger")

        Returns:
            True if this DER type maps to the given category.
        """
        return self.ha_device_category == ha_category


class DERRegistry:
    """Loads and queries the DER registry.

    Usage:
        registry = DERRegistry()
        registry.load()

        # Get all DER types
        all_ders = registry.entries

        # Find which DER types map to discovered HA device categories
        user_categories = ["thermostat", "smart_plug", "ev_charger"]
        matched = registry.get_der_types_for_categories(user_categories)

        # Get DER type IDs for VPP matching
        der_ids = registry.get_der_type_ids_for_categories(user_categories)

        # Get VPP-compatible DER types only
        vpp_ders = registry.get_vpp_compatible()
    """

    def __init__(self) -> None:
        """Initialize the DER registry."""
        self._entries: list[DEREntry] = []
        self._by_id: dict[str, DEREntry] = {}
        self._by_ha_category: dict[str, list[DEREntry]] = {}
        self._loaded = False

    @property
    def entries(self) -> list[DEREntry]:
        """Return all DER entries."""
        return self._entries

    @property
    def loaded(self) -> bool:
        """Return whether the registry has been loaded."""
        return self._loaded

    def load(self, file_path: Path | None = None) -> None:
        """Load DER data from the JSON registry file.

        Args:
            file_path: Optional override path (for testing). Defaults to
                       the bundled data/der_registry.json file.
        """
        path = file_path or _DER_REGISTRY_FILE

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _LOGGER.error("DER registry file not found: %s", path)
            self._entries = []
            self._loaded = False
            return
        except json.JSONDecodeError as err:
            _LOGGER.error("DER registry JSON parse error: %s", err)
            self._entries = []
            self._loaded = False
            return

        self._entries = []
        self._by_id = {}
        self._by_ha_category = {}

        for item in raw.get("der_types", []):
            try:
                typical_power_raw = item.get("typical_power_w")
                typical_power = None
                if typical_power_raw:
                    typical_power = DERTypicalPower(
                        min_w=typical_power_raw.get("min", 0),
                        max_w=typical_power_raw.get("max", 0),
                    )

                entry = DEREntry(
                    id=item["id"],
                    name=item["name"],
                    description=item.get("description", ""),
                    ha_domain=item["ha_domain"],
                    ha_device_category=item["ha_device_category"],
                    controllable_actions=item.get("controllable_actions", []),
                    energy_impact=item.get("energy_impact", "medium"),
                    typical_power=typical_power,
                    common_manufacturers=item.get("common_manufacturers", []),
                    vpp_compatible=item.get("vpp_compatible", False),
                    demand_response_role=item.get("demand_response_role", ""),
                )

                self._entries.append(entry)
                self._by_id[entry.id] = entry

                # Index by HA device category for fast lookups
                cat = entry.ha_device_category
                if cat not in self._by_ha_category:
                    self._by_ha_category[cat] = []
                self._by_ha_category[cat].append(entry)

            except (KeyError, TypeError) as err:
                _LOGGER.warning(
                    "Skipping invalid DER entry: %s — %s",
                    item.get("id", "?"),
                    err,
                )

        self._loaded = True
        _LOGGER.debug("Loaded %d DER type entries from registry", len(self._entries))

    def get_by_id(self, der_id: str) -> DEREntry | None:
        """Get a specific DER type by its ID."""
        return self._by_id.get(der_id)

    def get_vpp_compatible(self) -> list[DEREntry]:
        """Get all DER types that are VPP-compatible."""
        return [e for e in self._entries if e.vpp_compatible]

    def get_by_ha_category(self, ha_category: str) -> list[DEREntry]:
        """Get DER types that map to a given HA device category.

        Args:
            ha_category: Device category from the Controllable Devices sensor
                         (e.g., "thermostat", "smart_plug")

        Returns:
            List of matching DER entries.
        """
        return self._by_ha_category.get(ha_category, [])

    def get_der_types_for_categories(
        self,
        ha_categories: list[str],
    ) -> list[DEREntry]:
        """Get all DER types matching any of the given HA device categories.

        This is the primary method for connecting discovered HA devices
        to DER types (and subsequently to VPP programs).

        Args:
            ha_categories: List of device categories from Controllable Devices
                          (e.g., ["thermostat", "smart_plug", "ev_charger"])

        Returns:
            Deduplicated list of matching DER entries.
        """
        seen_ids: set[str] = set()
        results: list[DEREntry] = []
        for cat in ha_categories:
            for entry in self.get_by_ha_category(cat):
                if entry.id not in seen_ids:
                    seen_ids.add(entry.id)
                    results.append(entry)
        return results

    def get_der_type_ids_for_categories(
        self,
        ha_categories: list[str],
    ) -> list[str]:
        """Get DER type IDs for the given HA device categories.

        Returns IDs suitable for passing to VPPRegistry.get_matching_vpps().

        Args:
            ha_categories: List of device categories from Controllable Devices

        Returns:
            List of DER type ID strings.
        """
        return [e.id for e in self.get_der_types_for_categories(ha_categories)]

    def to_list(self) -> list[dict[str, Any]]:
        """Convert all entries to a list of dicts (for sensor attributes)."""
        return [e.to_dict() for e in self._entries]
