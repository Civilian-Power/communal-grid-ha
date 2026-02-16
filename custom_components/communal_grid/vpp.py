"""Virtual Power Plant (VPP) registry loader and query helpers.

Loads the VPP registry from the bundled JSON data file and provides
methods to filter VPPs by region, utility, and supported devices.

Device matching supports three modes:
  - Exact: model string must match exactly (default)
  - Prefix: model string must start with one of the listed prefixes
  - Wildcard: "*" matches any manufacturer or model

The JSON file (data/vpp_registry.json) can be updated independently
of the integration code — just edit the file and restart HA.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Path to the bundled VPP registry data file
_DATA_DIR = Path(__file__).parent / "data"
_VPP_REGISTRY_FILE = _DATA_DIR / "vpp_registry.json"


def _normalize_utility_name(name: str) -> str:
    """Normalize a utility name for fuzzy comparison.

    Strips common corporate suffixes (Co, Co., Company, Corp, Corp.,
    Corporation, Inc, Inc., LLC) and extra whitespace so that
    "Pacific Gas & Electric Co" matches "Pacific Gas & Electric".
    """
    import re

    normalized = name.strip().lower()
    # Remove trailing corporate suffixes (with optional period)
    normalized = re.sub(
        r"\s+(co\.?|company|corp\.?|corporation|inc\.?|llc|l\.l\.c\.)$",
        "",
        normalized,
    )
    # Collapse extra whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _utility_matches(registry_name: str, user_name: str) -> bool:
    """Check if a utility name from the VPP registry matches the user's utility.

    Uses normalized comparison to handle variations like
    'Pacific Gas & Electric' vs 'Pacific Gas & Electric Co'.
    """
    return _normalize_utility_name(registry_name) == _normalize_utility_name(user_name)


def _manufacturer_matches(required: str, actual: str | None) -> bool:
    """Check if a device manufacturer matches a VPP requirement.

    Case-insensitive comparison. Returns False if actual is None.
    """
    if not actual:
        return False
    return required.lower() == actual.lower()


def _model_matches(
    required_models: list[str],
    actual_model: str | None,
    match_type: str = "exact",
) -> bool:
    """Check if a device model matches a VPP requirement.

    Args:
        required_models: List of model strings to match against.
        actual_model: The model string from the discovered device.
        match_type: "exact" for exact match, "prefix" for starts-with.

    Returns:
        True if the actual model matches any of the required models.
    """
    if not actual_model:
        return False

    actual_lower = actual_model.lower()

    if match_type == "prefix":
        return any(actual_lower.startswith(m.lower()) for m in required_models)
    else:
        # Exact match (default)
        return any(actual_lower == m.lower() for m in required_models)


@dataclass
class VPPReward:
    """Reward structure for a VPP program."""

    type: str  # "per_kwh", "per_event", "flat_monthly", "flat_yearly"
    value: float | None  # dollar amount, or None if variable
    currency: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for sensor attributes."""
        return {
            "type": self.type,
            "value": self.value,
            "currency": self.currency,
            "description": self.description,
        }


@dataclass
class VPPRegion:
    """Geographic region a VPP program serves."""

    state: str  # two-letter state code, or "*" for all states
    utilities: list[str]  # utility names, or ["*"] for all utilities in state

    def matches(
        self,
        user_state: str | None = None,
        user_utility: str | None = None,
    ) -> bool:
        """Check if this region matches the user's state and utility.

        Args:
            user_state: Two-letter state code (e.g., "CA")
            user_utility: Utility name (e.g., "Pacific Gas & Electric")

        Returns:
            True if the region covers the user's location.
        """
        # Wildcard state matches everything
        if self.state == "*":
            if user_utility and self.utilities != ["*"]:
                return any(
                    _utility_matches(u, user_utility) for u in self.utilities
                )
            return True

        # Check state match
        if user_state and self.state.upper() != user_state.upper():
            return False

        # State matches — check utility
        if self.utilities == ["*"]:
            return True

        if user_utility:
            return any(
                _utility_matches(u, user_utility) for u in self.utilities
            )

        # State matches and no utility filter specified
        return True


@dataclass
class VPPSupportedDevice:
    """A specific device that a VPP program supports.

    Captures manufacturer/model-level compatibility, since VPP programs
    often only work with specific devices (e.g., TP-Link KP115 but not
    KP125M, or only Rheem water heaters with EcoNet Wi-Fi).
    """

    der_type: str  # DER type ID (e.g., "smart_plug", "smart_thermostat")
    manufacturer: str  # Manufacturer name, or "*" for any
    models: list[str]  # Model names/prefixes, or ["*"] for any
    match_type: str  # "exact" or "prefix"
    notes: str | None  # Human-readable compatibility note

    def matches_device(
        self,
        manufacturer: str | None = None,
        model: str | None = None,
    ) -> bool:
        """Check if a discovered device matches this supported device entry.

        Args:
            manufacturer: Device manufacturer from HA device registry.
            model: Device model from HA device registry.

        Returns:
            True if the device matches this entry's criteria.
        """
        # Check manufacturer
        if self.manufacturer != "*":
            if not _manufacturer_matches(self.manufacturer, manufacturer):
                return False

        # Check model
        if self.models != ["*"]:
            if not _model_matches(self.models, model, self.match_type):
                return False

        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for sensor attributes."""
        return {
            "der_type": self.der_type,
            "manufacturer": self.manufacturer,
            "models": self.models,
            "match_type": self.match_type,
            "notes": self.notes,
        }


@dataclass
class VPPEntry:
    """A Virtual Power Plant program entry."""

    id: str
    name: str
    provider: str
    description: str
    regions: list[VPPRegion]
    enrollment_url: str
    management_url: str | None
    supported_devices: list[VPPSupportedDevice]
    reward: VPPReward
    active: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for sensor attributes."""
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "description": self.description,
            "enrollment_url": self.enrollment_url,
            "management_url": self.management_url,
            "supported_devices": [sd.to_dict() for sd in self.supported_devices],
            "reward": self.reward.to_dict(),
            "active": self.active,
            "regions": [
                {"state": r.state, "utilities": r.utilities}
                for r in self.regions
            ],
        }

    def serves_region(
        self,
        state: str | None = None,
        utility: str | None = None,
    ) -> bool:
        """Check if this VPP serves a given state/utility."""
        return any(r.matches(state, utility) for r in self.regions)

    def supports_der_type(self, der_type: str) -> bool:
        """Check if this VPP supports a given DER type (any manufacturer/model).

        This is a broad check — returns True if ANY supported_devices entry
        has the given der_type, regardless of manufacturer/model.
        """
        return any(sd.der_type == der_type for sd in self.supported_devices)

    def supports_device(
        self,
        der_type: str,
        manufacturer: str | None = None,
        model: str | None = None,
    ) -> bool:
        """Check if this VPP supports a specific device by type + manufacturer + model.

        This is the precise check that accounts for model-level compatibility.

        Args:
            der_type: DER type ID (e.g., "smart_plug")
            manufacturer: Device manufacturer (e.g., "TP-Link")
            model: Device model (e.g., "KP115")

        Returns:
            True if the VPP supports this exact device.
        """
        for sd in self.supported_devices:
            if sd.der_type != der_type:
                continue
            if sd.matches_device(manufacturer, model):
                return True
        return False

    def get_supported_devices_for_type(self, der_type: str) -> list[VPPSupportedDevice]:
        """Get all supported device entries for a given DER type."""
        return [sd for sd in self.supported_devices if sd.der_type == der_type]


class VPPRegistry:
    """Loads and queries the VPP registry.

    Usage:
        registry = VPPRegistry()
        registry.load()

        # Get all VPPs available in California for PG&E customers
        vpps = registry.get_vpps_for_region(state="CA", utility="Pacific Gas & Electric")

        # Check if a specific device is supported by any VPP
        vpps = registry.get_vpps_for_device(
            der_type="smart_plug",
            manufacturer="TP-Link",
            model="KP115",
        )

        # Get VPPs matching region AND a specific device
        vpps = registry.get_matching_vpps(
            state="CA",
            utility="Pacific Gas & Electric",
            devices=[
                {"der_type": "smart_plug", "manufacturer": "TP-Link", "model": "KP115"},
                {"der_type": "smart_thermostat", "manufacturer": "Google", "model": "Nest Learning Thermostat"},
            ],
        )
    """

    def __init__(self) -> None:
        """Initialize the VPP registry."""
        self._entries: list[VPPEntry] = []
        self._loaded = False

    @property
    def entries(self) -> list[VPPEntry]:
        """Return all VPP entries."""
        return self._entries

    @property
    def loaded(self) -> bool:
        """Return whether the registry has been loaded."""
        return self._loaded

    def load(self, file_path: Path | None = None) -> None:
        """Load VPP data from the JSON registry file.

        Args:
            file_path: Optional override path (for testing). Defaults to
                       the bundled data/vpp_registry.json file.
        """
        path = file_path or _VPP_REGISTRY_FILE

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _LOGGER.error("VPP registry file not found: %s", path)
            self._entries = []
            self._loaded = False
            return
        except json.JSONDecodeError as err:
            _LOGGER.error("VPP registry JSON parse error: %s", err)
            self._entries = []
            self._loaded = False
            return

        self._entries = []
        for item in raw.get("vpps", []):
            try:
                # Parse supported_devices (v2 schema)
                supported_devices = []
                for sd in item.get("supported_devices", []):
                    supported_devices.append(
                        VPPSupportedDevice(
                            der_type=sd["der_type"],
                            manufacturer=sd.get("manufacturer", "*"),
                            models=sd.get("models", ["*"]),
                            match_type=sd.get("match_type", "exact"),
                            notes=sd.get("notes"),
                        )
                    )

                entry = VPPEntry(
                    id=item["id"],
                    name=item["name"],
                    provider=item["provider"],
                    description=item.get("description", ""),
                    regions=[
                        VPPRegion(state=r["state"], utilities=r.get("utilities", ["*"]))
                        for r in item.get("regions", [])
                    ],
                    enrollment_url=item.get("enrollment_url", ""),
                    management_url=item.get("management_url"),
                    supported_devices=supported_devices,
                    reward=VPPReward(
                        type=item["reward"]["type"],
                        value=item["reward"].get("value"),
                        currency=item["reward"].get("currency", "USD"),
                        description=item["reward"].get("description", ""),
                    ),
                    active=item.get("active", True),
                )
                self._entries.append(entry)
            except (KeyError, TypeError) as err:
                _LOGGER.warning("Skipping invalid VPP entry: %s — %s", item.get("id", "?"), err)

        self._loaded = True
        _LOGGER.debug("Loaded %d VPP entries from registry", len(self._entries))

    def get_by_id(self, vpp_id: str) -> VPPEntry | None:
        """Get a specific VPP by its ID."""
        for entry in self._entries:
            if entry.id == vpp_id:
                return entry
        return None

    def get_active(self) -> list[VPPEntry]:
        """Get all active VPP programs."""
        return [e for e in self._entries if e.active]

    def get_vpps_for_region(
        self,
        state: str | None = None,
        utility: str | None = None,
        active_only: bool = True,
    ) -> list[VPPEntry]:
        """Get VPPs that serve a given region.

        Args:
            state: Two-letter state code (e.g., "CA")
            utility: Utility company name
            active_only: Only return active programs (default True)

        Returns:
            List of matching VPP entries.
        """
        results = []
        for entry in self._entries:
            if active_only and not entry.active:
                continue
            if entry.serves_region(state, utility):
                results.append(entry)
        return results

    def get_vpps_for_der_type(
        self,
        der_type: str,
        active_only: bool = True,
    ) -> list[VPPEntry]:
        """Get VPPs that support a given DER type (broad category match).

        This does NOT check specific manufacturer/model — use
        get_vpps_for_device() for precise matching.

        Args:
            der_type: DER type ID (e.g., "smart_thermostat", "ev_charger")
            active_only: Only return active programs (default True)

        Returns:
            List of matching VPP entries.
        """
        results = []
        for entry in self._entries:
            if active_only and not entry.active:
                continue
            if entry.supports_der_type(der_type):
                results.append(entry)
        return results

    def get_vpps_for_device(
        self,
        der_type: str,
        manufacturer: str | None = None,
        model: str | None = None,
        active_only: bool = True,
    ) -> list[VPPEntry]:
        """Get VPPs that support a specific device by type + manufacturer + model.

        This is the precise query that checks model-level compatibility.

        Args:
            der_type: DER type ID (e.g., "smart_plug")
            manufacturer: Device manufacturer (e.g., "TP-Link")
            model: Device model (e.g., "KP115")
            active_only: Only return active programs

        Returns:
            List of VPP entries that support this exact device.
        """
        results = []
        for entry in self._entries:
            if active_only and not entry.active:
                continue
            if entry.supports_device(der_type, manufacturer, model):
                results.append(entry)
        return results

    def get_matching_vpps(
        self,
        state: str | None = None,
        utility: str | None = None,
        devices: list[dict[str, str | None]] | None = None,
        der_types: list[str] | None = None,
        active_only: bool = True,
    ) -> list[VPPEntry]:
        """Get VPPs matching region AND supporting at least one device.

        This is the primary query method for the future filtering view.
        Supports both precise device matching and broad DER type matching.

        Args:
            state: Two-letter state code
            utility: Utility company name
            devices: List of dicts with "der_type", "manufacturer", "model"
                     keys — for precise model-level matching.
            der_types: List of DER type IDs — for broad category matching
                       (used as fallback if devices not provided).
            active_only: Only return active programs

        Returns:
            List of VPP entries that serve the region and support
            at least one of the specified devices.
        """
        results = []
        for entry in self._entries:
            if active_only and not entry.active:
                continue
            if not entry.serves_region(state, utility):
                continue

            # Check device-level matching (precise)
            if devices:
                matched = any(
                    entry.supports_device(
                        d["der_type"],
                        d.get("manufacturer"),
                        d.get("model"),
                    )
                    for d in devices
                )
                if not matched:
                    continue
            # Fallback to broad DER type matching
            elif der_types:
                if not any(entry.supports_der_type(dt) for dt in der_types):
                    continue

            results.append(entry)
        return results

    def to_list(self, active_only: bool = True) -> list[dict[str, Any]]:
        """Convert all entries to a list of dicts (for sensor attributes).

        Args:
            active_only: Only include active programs

        Returns:
            List of VPP dictionaries.
        """
        entries = self.get_active() if active_only else self._entries
        return [e.to_dict() for e in entries]
