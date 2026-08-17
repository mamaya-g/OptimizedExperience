"""Guest preferences: per-attraction tiers, water-ride weather comfort, and the
day-level settings from Plan 2 (Lightning Lane toggle, walking pace,
navigation strategy, arrival/departure window, meal/shopping blocks). All of
these live in the one preferences.yaml the guest already edits -- see
cli.py's --watch loop, which reloads this file every tick so a mid-day change
(e.g. flipping use_lightning_lane) takes effect without restarting.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel


class PreferenceTier(str, Enum):
    MUST_GO = "MUST_GO"
    NICE_TO_HAVE = "NICE_TO_HAVE"
    SKIP = "SKIP"


class WaterRideComfort(str, Enum):
    MIND_IF_COOL = "MIND_IF_COOL"
    DONT_MIND = "DONT_MIND"
    PREFER_AFTERNOON = "PREFER_AFTERNOON"


class WalkingPace(str, Enum):
    SLOW = "SLOW"
    AVERAGE = "AVERAGE"
    FAST = "FAST"


class NavigationStrategy(str, Enum):
    TIME_OPTIMAL = "TIME_OPTIMAL"
    LAND_ORDER = "LAND_ORDER"
    CLUSTERED = "CLUSTERED"


class BlockPlacement(str, Enum):
    PREFERRED_RANGE = "PREFERRED_RANGE"
    FIXED_TIME = "FIXED_TIME"
    SOLVER_CHOICE = "SOLVER_CHOICE"


class ActivityKind(str, Enum):
    """Only affects SOLVER_CHOICE placement (see planning.build_activity_nodes):
    gives the solver a sensible default hour-of-day window instead of "any
    time all day," which would otherwise let a mandatory block's forcing
    prize get grabbed at 8am just because that's the first opportunity."""

    LUNCH = "LUNCH"
    DINNER = "DINNER"
    SNACK = "SNACK"
    SHOPPING = "SHOPPING"
    OTHER = "OTHER"


class ActivityBlock(BaseModel):
    """A meal or shopping block. Modeled as a mandatory Node in planning.py
    (see build_activity_nodes()), reusing the existing show-style
    future-window scheduling machinery rather than a parallel subsystem."""

    name: str
    duration_minutes: float
    placement: BlockPlacement
    kind: ActivityKind = ActivityKind.OTHER
    range_start: datetime | None = None  # PREFERRED_RANGE
    range_end: datetime | None = None  # PREFERRED_RANGE
    fixed_time: datetime | None = None  # FIXED_TIME
    mandatory: bool = True


_TIER_BASE_PRIZE = {
    PreferenceTier.MUST_GO: 100.0,
    PreferenceTier.NICE_TO_HAVE: 40.0,
}

# Unlisted attractions get a low, nonzero prize so the optimizer can still
# opportunistically slot them in when time allows.
DEFAULT_BASE_PRIZE = 10.0


class Preferences(BaseModel):
    water_ride_comfort: WaterRideComfort = WaterRideComfort.MIND_IF_COOL
    tiers: dict[str, PreferenceTier] = {}
    use_lightning_lane: bool = True
    walking_pace: WalkingPace = WalkingPace.AVERAGE
    navigation_strategy: NavigationStrategy = NavigationStrategy.TIME_OPTIMAL
    land_order: list[str] = []
    planned_arrival: datetime | None = None
    planned_departure: datetime | None = None
    activity_blocks: list[ActivityBlock] = []
    # Attraction id/slug -> desired visit count (e.g. 2 = ride it twice).
    # Advanced/secondary setting -- absent or 1 means "once, same as always."
    repeat_counts: dict[str, int] = {}

    def base_prize_for(self, slug: str | None, entity_id: str) -> float | None:
        """Returns None if the guest tagged this attraction SKIP (exclude from candidates)."""
        tier = self.tier_for(slug, entity_id)
        if tier is None:
            return DEFAULT_BASE_PRIZE
        if tier is PreferenceTier.SKIP:
            return None
        return _TIER_BASE_PRIZE[tier]

    def tier_for(self, slug: str | None, entity_id: str) -> PreferenceTier | None:
        """Same tier system for shows as attractions -- a parade/nighttime
        show tagged MUST_GO is treated as mandatory in planning.py (guaranteed
        a scheduling attempt, honestly reported if it truly can't fit),
        exactly like a meal block. This deliberately allows *any number* of
        must-see shows, not just one -- a day can run several shows a guest
        wants, and a single-pick toggle previously made that impossible."""
        if slug and slug in self.tiers:
            return self.tiers[slug]
        return self.tiers.get(entity_id)


def load_preferences(path: Path) -> Preferences:
    raw = yaml.safe_load(path.read_text()) or {}
    return Preferences.model_validate(raw)
