"""Show category mapping: hand-seeded, since no API field distinguishes a
parade from a nighttime fireworks/projection show from incidental street
entertainment -- they're all just `entityType: "SHOW"`. Same pattern as
lands.py/reliability.py. Unmapped shows fall back to "OTHER", which never
gets the mandatory-if-requested treatment build_candidate_nodes() gives to
PARADE/NIGHTTIME_SPECTACULAR.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

ShowCategory = str  # "PARADE" | "NIGHTTIME_SPECTACULAR" | "OTHER" -- see optimizer.contracts.ShowCategory


class ShowCategoryMap(BaseModel):
    categories: dict[str, ShowCategory] = {}

    def category_for(self, slug: str | None, entity_id: str) -> ShowCategory:
        if slug and slug in self.categories:
            return self.categories[slug]
        return self.categories.get(entity_id, "OTHER")


def load_show_category_map(path: Path) -> ShowCategoryMap:
    raw = yaml.safe_load(path.read_text()) or {}
    return ShowCategoryMap.model_validate(raw)
