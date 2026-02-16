"""TOU rate calculation engine.

Parses OpenEI rate schedule data and determines the current electricity
rate based on time of day, day of week, and season.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, date
from typing import Any

from .const import (
    SEASON_SUMMER,
    SEASON_WINTER,
    SUMMER_START_MONTH,
    SUMMER_END_MONTH,
    TIER_PEAK,
    TIER_OFF_PEAK,
    TIER_PARTIAL_PEAK,
    TIER_SUPER_OFF_PEAK,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class RatePeriod:
    """A single rate period (e.g., 'Peak weekday 4pm-9pm')."""

    tier: str
    rate: float
    start_hour: int
    end_hour: int
    weekdays_only: bool = False
    weekends_only: bool = False

    def matches(self, hour: int, is_weekend: bool) -> bool:
        """Check if this period matches the given time."""
        if self.weekdays_only and is_weekend:
            return False
        if self.weekends_only and not is_weekend:
            return False

        if self.start_hour <= self.end_hour:
            return self.start_hour <= hour < self.end_hour
        else:
            return hour >= self.start_hour or hour < self.end_hour


@dataclass
class SeasonSchedule:
    """Rate schedule for a single season (summer or winter)."""

    season: str
    periods: list[RatePeriod] = field(default_factory=list)


@dataclass
class RateSchedule:
    """Complete parsed rate schedule for a utility plan."""

    utility_name: str
    rate_plan_name: str
    description: str
    effective_date: str
    seasons: dict[str, SeasonSchedule] = field(default_factory=dict)
    fallback_rate: float = 0.0
    fallback_tier: str = TIER_OFF_PEAK


@dataclass
class CurrentRate:
    """The current rate calculation result."""

    rate: float
    tier: str
    season: str
    next_change: datetime | None = None
    rate_plan: str = ""
    utility: str = ""


class RateCalculator:
    """Calculates the current electricity rate from a parsed schedule."""

    def __init__(self, schedule: RateSchedule) -> None:
        """Initialize with a parsed rate schedule."""
        self._schedule = schedule

    def get_current_rate(self, now: datetime) -> CurrentRate:
        """Determine the current rate at the given time."""
        season = self._get_season(now.date())
        is_weekend = now.weekday() >= 5
        hour = now.hour

        season_schedule = self._schedule.seasons.get(season)
        if not season_schedule:
            _LOGGER.warning("No schedule found for season '%s', using fallback", season)
            return CurrentRate(
                rate=self._schedule.fallback_rate,
                tier=self._schedule.fallback_tier,
                season=season,
                rate_plan=self._schedule.rate_plan_name,
                utility=self._schedule.utility_name,
            )

        for period in season_schedule.periods:
            if period.matches(hour, is_weekend):
                next_change = self._calc_next_change(now, season_schedule, is_weekend)
                return CurrentRate(
                    rate=period.rate,
                    tier=period.tier,
                    season=season,
                    next_change=next_change,
                    rate_plan=self._schedule.rate_plan_name,
                    utility=self._schedule.utility_name,
                )

        _LOGGER.warning(
            "No rate period matched for hour=%d, weekend=%s, season=%s. Using fallback.",
            hour, is_weekend, season,
        )
        return CurrentRate(
            rate=self._schedule.fallback_rate,
            tier=self._schedule.fallback_tier,
            season=season,
            rate_plan=self._schedule.rate_plan_name,
            utility=self._schedule.utility_name,
        )

    def _get_season(self, d: date) -> str:
        """Determine the season for a given date."""
        if SUMMER_START_MONTH <= d.month <= SUMMER_END_MONTH:
            return SEASON_SUMMER
        return SEASON_WINTER

    def _calc_next_change(
        self, now: datetime, season_schedule: SeasonSchedule, is_weekend: bool,
    ) -> datetime | None:
        """Calculate when the next rate tier change occurs."""
        current_hour = now.hour

        transitions = set()
        for period in season_schedule.periods:
            if period.weekdays_only and is_weekend:
                continue
            if period.weekends_only and not is_weekend:
                continue
            transitions.add(period.start_hour)
            if period.end_hour <= 23:
                transitions.add(period.end_hour)

        transitions = sorted(transitions)

        for t_hour in transitions:
            if t_hour > current_hour:
                return now.replace(hour=t_hour, minute=0, second=0, microsecond=0)

        tomorrow = now + timedelta(days=1)
        tomorrow_is_weekend = tomorrow.weekday() >= 5

        tomorrow_transitions = set()
        for period in season_schedule.periods:
            if period.weekdays_only and tomorrow_is_weekend:
                continue
            if period.weekends_only and not tomorrow_is_weekend:
                continue
            tomorrow_transitions.add(period.start_hour)

        if tomorrow_transitions:
            first_hour = min(tomorrow_transitions)
            return tomorrow.replace(hour=first_hour, minute=0, second=0, microsecond=0)

        return None


def parse_openei_schedule(api_data: dict[str, Any]) -> RateSchedule:
    """Parse the OpenEI API response into a RateSchedule."""
    utility_name = api_data.get("utility", "Unknown Utility")
    rate_plan_name = api_data.get("name", "") or api_data.get("label", "Unknown Plan")
    description = api_data.get("description", "")
    effective_date = api_data.get("startdate", "")

    schedule = RateSchedule(
        utility_name=utility_name,
        rate_plan_name=rate_plan_name,
        description=description,
        effective_date=effective_date,
    )

    energy_rates = api_data.get("energyratestructure", [])
    weekday_schedule = api_data.get("energyweekdayschedule", [])
    weekend_schedule = api_data.get("energyweekendschedule", [])

    if not energy_rates or not weekday_schedule:
        _LOGGER.warning(
            "Rate plan '%s' has no TOU structure. It may be a flat-rate or tiered plan.",
            rate_plan_name,
        )
        flat_rate = _extract_flat_rate(api_data)
        if flat_rate is not None:
            for season_name in [SEASON_SUMMER, SEASON_WINTER]:
                schedule.seasons[season_name] = SeasonSchedule(
                    season=season_name,
                    periods=[RatePeriod(tier=TIER_OFF_PEAK, rate=flat_rate, start_hour=0, end_hour=24)],
                )
            schedule.fallback_rate = flat_rate
        return schedule

    period_rates: dict[int, float] = {}
    for period_idx, tiers in enumerate(energy_rates):
        if tiers and isinstance(tiers, list):
            tier_data = tiers[0] if isinstance(tiers[0], dict) else {}
            rate_val = tier_data.get("rate", 0.0)
            rate_val += tier_data.get("adj", 0.0)
            period_rates[period_idx] = rate_val

    _LOGGER.debug("Period rates extracted: %s", period_rates)

    tier_names = _assign_tier_names(period_rates)

    for season_name, start_month, end_month in [
        (SEASON_SUMMER, SUMMER_START_MONTH - 1, SUMMER_END_MONTH - 1),
        (SEASON_WINTER, 0, SUMMER_START_MONTH - 2),
    ]:
        season_schedule = SeasonSchedule(season=season_name)
        representative_month = start_month

        if representative_month < len(weekday_schedule):
            weekday_hours = weekday_schedule[representative_month]
            weekday_periods = _hours_to_periods(
                weekday_hours, period_rates, tier_names, weekdays_only=True
            )
            season_schedule.periods.extend(weekday_periods)

        if weekend_schedule and representative_month < len(weekend_schedule):
            weekend_hours = weekend_schedule[representative_month]
            weekend_periods = _hours_to_periods(
                weekend_hours, period_rates, tier_names, weekends_only=True
            )
            season_schedule.periods.extend(weekend_periods)
        else:
            for period in list(season_schedule.periods):
                period.weekdays_only = False

        schedule.seasons[season_name] = season_schedule

    if period_rates:
        schedule.fallback_rate = min(period_rates.values())

    _LOGGER.info(
        "Parsed rate schedule: %s (%s) with %d seasons",
        rate_plan_name, utility_name, len(schedule.seasons),
    )

    return schedule


def _extract_flat_rate(api_data: dict[str, Any]) -> float | None:
    """Try to extract a flat rate from the API data."""
    energy_rates = api_data.get("energyratestructure", [])
    if energy_rates and energy_rates[0]:
        first_tier = energy_rates[0][0] if isinstance(energy_rates[0], list) else {}
        if isinstance(first_tier, dict):
            return first_tier.get("rate", None)
    return None


def _assign_tier_names(period_rates: dict[int, float]) -> dict[int, str]:
    """Assign human-readable tier names based on rate values."""
    if not period_rates:
        return {}

    unique_rates = sorted(set(period_rates.values()))
    num_unique = len(unique_rates)

    tier_names: dict[int, str] = {}
    for period_idx, rate_val in period_rates.items():
        if num_unique <= 1:
            tier_names[period_idx] = TIER_OFF_PEAK
        elif num_unique == 2:
            tier_names[period_idx] = TIER_PEAK if rate_val == unique_rates[-1] else TIER_OFF_PEAK
        elif num_unique == 3:
            if rate_val == unique_rates[-1]:
                tier_names[period_idx] = TIER_PEAK
            elif rate_val == unique_rates[0]:
                tier_names[period_idx] = TIER_OFF_PEAK
            else:
                tier_names[period_idx] = TIER_PARTIAL_PEAK
        else:
            if rate_val == unique_rates[-1]:
                tier_names[period_idx] = TIER_PEAK
            elif rate_val == unique_rates[0]:
                tier_names[period_idx] = TIER_SUPER_OFF_PEAK
            elif rate_val == unique_rates[-2]:
                tier_names[period_idx] = TIER_PARTIAL_PEAK
            else:
                tier_names[period_idx] = TIER_OFF_PEAK

    return tier_names


def _hours_to_periods(
    hour_schedule: list[int],
    period_rates: dict[int, float],
    tier_names: dict[int, str],
    weekdays_only: bool = False,
    weekends_only: bool = False,
) -> list[RatePeriod]:
    """Convert an hour-by-hour schedule into consolidated RatePeriods."""
    if not hour_schedule or len(hour_schedule) < 24:
        return []

    periods: list[RatePeriod] = []
    current_period_idx = hour_schedule[0]
    start_hour = 0

    for hour in range(1, 25):
        period_idx = hour_schedule[hour] if hour < 24 else -1

        if period_idx != current_period_idx:
            rate = period_rates.get(current_period_idx, 0.0)
            tier = tier_names.get(current_period_idx, TIER_OFF_PEAK)

            periods.append(
                RatePeriod(
                    tier=tier, rate=rate,
                    start_hour=start_hour,
                    end_hour=hour if hour <= 24 else 24,
                    weekdays_only=weekdays_only,
                    weekends_only=weekends_only,
                )
            )

            current_period_idx = period_idx
            start_hour = hour

    return periods
