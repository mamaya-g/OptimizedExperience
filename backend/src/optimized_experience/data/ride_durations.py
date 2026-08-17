"""Attraction ride-duration mapping: hand-seeded, since no API exposes actual
ride length (themeparks.wiki doesn't return duration data at all). Same
pattern as lands.py/reliability.py. Unmapped attractions fall back to
DEFAULT_DURATION_MINUTES -- a guess, not a measurement, same disclosed-
simplification status the flat default always had, just now only applying
to genuinely unmapped attractions instead of every single one.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

# Used only when an attraction isn't in the seed data below.
DEFAULT_DURATION_MINUTES = 4.0


class RideDurationMap(BaseModel):
    durations: dict[str, float] = {}

    def duration_for(self, slug: str | None, entity_id: str) -> float:
        if slug and slug in self.durations:
            return self.durations[slug]
        return self.durations.get(entity_id, DEFAULT_DURATION_MINUTES)


def load_ride_duration_map(path: Path) -> RideDurationMap:
    raw = yaml.safe_load(path.read_text()) or {}
    return RideDurationMap.model_validate(raw)
