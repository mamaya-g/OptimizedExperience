"""Attraction reliability + water-ride tagging: hand-seeded now, intended to be
replaced by a real self-collected history once `scripts/collect_status_log.py`
has accumulated enough snapshots (that migration is a documented future step,
not built in this phase — see the plan).

No public API exposes Disneyland-specific breakdown history, so the tiers
below are a qualitative starting point (complex show-scene/animatronic-heavy
attractions tend to be less reliable), not a claim of measured failure rates.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel

from optimized_experience.data.models import LiveDataEntry


class ReliabilityTier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ReliabilityProfile(BaseModel):
    default_tier: ReliabilityTier = ReliabilityTier.MEDIUM
    reliability: dict[str, ReliabilityTier] = {}
    water_rides: set[str] = set()

    def tier_for(self, slug: str | None, entity_id: str) -> ReliabilityTier:
        if slug and slug in self.reliability:
            return self.reliability[slug]
        return self.reliability.get(entity_id, self.default_tier)

    def is_water_ride(self, slug: str | None, entity_id: str) -> bool:
        return (slug is not None and slug in self.water_rides) or entity_id in self.water_rides


def load_reliability_profile(path: Path) -> ReliabilityProfile:
    raw = yaml.safe_load(path.read_text()) or {}
    return ReliabilityProfile.model_validate(raw)


STATUS_LOG_COLUMNS = ["timestamp_utc", "entity_id", "name", "entity_type", "status"]


def append_status_snapshot(log_path: Path, live_entries: list[LiveDataEntry]) -> None:
    """Appends one timestamped status row per entity — the seed of a real,
    self-collected reliability dataset over time. Called by
    `scripts/collect_status_log.py`, typically on a cron schedule."""
    file_exists = log_path.exists()
    timestamp = datetime.now(timezone.utc).isoformat()
    with log_path.open("a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(STATUS_LOG_COLUMNS)
        for entry in live_entries:
            writer.writerow([timestamp, entry.id, entry.name, entry.entityType, entry.status or ""])
