"""Live park data access: a DataSource Protocol with a real (themeparks.wiki) and
a replay (fixture-backed) implementation, so the optimizer can be exercised
end-to-end without a live park visit or park operating hours.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

import httpx

from optimized_experience.data.cache import InProcessTTLCache
from optimized_experience.data.models import ChildrenResponse, LiveResponse, ScheduleResponse

THEMEPARKS_WIKI_BASE_URL = "https://api.themeparks.wiki/v1"

DISNEYLAND_PARK_ID = "7340550b-c14d-4def-80bb-acdb51d49a66"
DISNEYLAND_RESORT_DESTINATION_ID = "bfc89fd6-314d-44b4-b89e-df1a89cf991e"

_LIVE_TTL_SECONDS = 120
_STATIC_TTL_SECONDS = 3600


class DataSource(Protocol):
    def get_children(self) -> ChildrenResponse: ...
    def get_live(self) -> LiveResponse: ...
    def get_schedule(self) -> ScheduleResponse: ...


class ThemeParksWikiSource:
    """Real HTTP client against api.themeparks.wiki/v1 for a single park."""

    def __init__(
        self,
        park_id: str = DISNEYLAND_PARK_ID,
        base_url: str = THEMEPARKS_WIKI_BASE_URL,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._park_id = park_id
        self._client = httpx.Client(base_url=base_url, timeout=timeout_seconds)
        self._live_cache = InProcessTTLCache(ttl_seconds=_LIVE_TTL_SECONDS)
        self._static_cache = InProcessTTLCache(ttl_seconds=_STATIC_TTL_SECONDS)

    def get_children(self) -> ChildrenResponse:
        return self._static_cache.get_or_set(
            "children",
            lambda: ChildrenResponse.model_validate(
                self._client.get(f"/entity/{self._park_id}/children").raise_for_status().json()
            ),
        )

    def get_live(self) -> LiveResponse:
        return self._live_cache.get_or_set(
            "live",
            lambda: LiveResponse.model_validate(
                self._client.get(f"/entity/{self._park_id}/live").raise_for_status().json()
            ),
        )

    def get_schedule(self) -> ScheduleResponse:
        return self._static_cache.get_or_set(
            "schedule",
            lambda: ScheduleResponse.model_validate(
                self._client.get(f"/entity/{self._park_id}/schedule").raise_for_status().json()
            ),
        )

    def close(self) -> None:
        self._client.close()


class ReplayDataSource:
    """Fixture-backed DataSource for offline demos and tests.

    Expects a directory containing `children.json`, `live.json`, `schedule.json`
    with the same shapes as the real API responses.
    """

    def __init__(self, fixture_dir: Path) -> None:
        self._fixture_dir = fixture_dir

    def _load(self, filename: str) -> dict:
        return json.loads((self._fixture_dir / filename).read_text())

    def get_children(self) -> ChildrenResponse:
        return ChildrenResponse.model_validate(self._load("children.json"))

    def get_live(self) -> LiveResponse:
        return LiveResponse.model_validate(self._load("live.json"))

    def get_schedule(self) -> ScheduleResponse:
        return ScheduleResponse.model_validate(self._load("schedule.json"))
