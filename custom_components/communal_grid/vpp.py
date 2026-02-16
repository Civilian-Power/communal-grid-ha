"""Virtual Power Plant (VPP) registry loader and query helpers.

Loads the VPP registry from the bundled JSON data file and provides
methods to filter VPPs by region, utility, and supported device types.

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
                    u.lower() == user_utility.lower() for u in self.utilities
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
                u.lower() == user_utility.lower() for u in self.utilities
            )

        # State matches and no utility filter specified
        return True


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
    supported_der_types: list[str]
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
            "supported_der_types": self.supported_der_types,
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
        """Check if this VPP supports a given DER device type."""
        return der_type in self.supported_der_types


class VPPRegistry:
    """Loads and queries the VPP registry.

    Usage:
        registry = VPPRegistry()
        registry.load()

        # Get all VPPs available in California for PG&E customers
        vpps = registry.get_vpps_for_region(state="CA", utility="Pacific Gas & Electric")

        # Get VPPs that support smart thermostats
        vpps = registry.get_vpps_for_der_type("smart_thermostat")

        # Get VPPs matching both region and device type
        vpps = registry.get_matching_vpps(
            state="CA",
            utility="Pacific Gas & Electric",
            der_types=["smart_thermostat", "ev_charger"],
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
                    supported_der_types=item.get("supported_der_types", []),
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
        """Get VPPs that support a given DER device type.

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

    def get_matching_vpps(
        self,
        state: str | None = None,
        utility: str | None = None,
        der_types: list[str] | None = None,
        active_only: bool = True,
    ) -> list[VPPEntry]:
        """Get VPPs matching region AND supporting at least one DER type.

        This is the primary query method for the future filtering view.

        Args:
            state: Two-letter state code
            utility: Utility company name
            der_types: List of DER type IDs the user has
            active_only: Only return active programs

        Returns:
            List of VPP entries that serve the region and support
            at least one of the specified DER types.
        """
        results = []
        for entry in self._entries:
            if active_only and not entry.active:
                continue
            if not entry.serves_region(state, utility):
                continue
            if der_types and not any(
                entry.supports_der_type(dt) for dt in der_types
            ):
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
