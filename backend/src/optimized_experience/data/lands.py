"""Attraction-to-land mapping: hand-seeded, since no API exposes Disneyland's
land groupings. Same pattern as reliability.py. Unmapped attractions fall
back to land=None, treated as "any land" downstream (see optimizer/navigation.py)
so a gap in the seed data never hard-blocks scheduling.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class LandMap(BaseModel):
    lands: dict[str, str] = {}

    def land_for(self, slug: str | None, entity_id: str) -> str | None:
        if slug and slug in self.lands:
            return self.lands[slug]
        return self.lands.get(entity_id)


def load_land_map(path: Path) -> LandMap:
    raw = yaml.safe_load(path.read_text()) or {}
    return LandMap.model_validate(raw)
