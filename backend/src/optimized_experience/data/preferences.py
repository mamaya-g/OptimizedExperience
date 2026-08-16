"""Guest preferences: per-attraction tiers plus water-ride weather comfort."""

from __future__ import annotations

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

    def base_prize_for(self, slug: str | None, entity_id: str) -> float | None:
        """Returns None if the guest tagged this attraction SKIP (exclude from candidates)."""
        tier = self._tier_for(slug, entity_id)
        if tier is None:
            return DEFAULT_BASE_PRIZE
        if tier is PreferenceTier.SKIP:
            return None
        return _TIER_BASE_PRIZE[tier]

    def _tier_for(self, slug: str | None, entity_id: str) -> PreferenceTier | None:
        if slug and slug in self.tiers:
            return self.tiers[slug]
        return self.tiers.get(entity_id)


def load_preferences(path: Path) -> Preferences:
    raw = yaml.safe_load(path.read_text()) or {}
    return Preferences.model_validate(raw)
