"""FastAPI backend exposing the itinerary planner over HTTP -- the live-data
counterpart to the CLI, for the Next.js itinerary viewer (frontend/).

Stateless per request except for the live data sources (_data_source,
_weather_source), which persist for the server's process lifetime so the
existing TTL caching (data/cache.py) actually helps across concurrent
requests instead of hitting themeparks.wiki/NWS fresh every time -- the same
reason cli.py's --watch loop builds its sources once outside the loop.

Always live (no --replay equivalent): this is the "does this work end to end
with live data" surface, not a demo/test entrypoint -- see scripts/demo_plan.py
and the test suite's ReplayDataSource usage for offline verification instead.

Reliability/land-map/ride-duration/show-category config are reloaded from disk
on every request (cheap YAML parsing), matching --watch's per-tick reload --
editing those files takes effect on the next request without restarting the
server. Guest preferences, by contrast, are no longer file-based for this API:
POST /api/plan takes the full Preferences object as its request body, since
the frontend now collects them in the browser (localStorage), not from a
server-side preferences.yaml -- that file remains the CLI's own input, untouched.
Objective is still a query param; the solver is always OR-Tools here (the
solver choice is a CLI/demo concern, not something the primary UI exposes).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from optimized_experience.cli import DEFAULT_CONFIG_DIR, build_sources, generate_plan
from optimized_experience.data.lands import load_land_map
from optimized_experience.data.models import PriceInfo
from optimized_experience.data.preferences import Preferences
from optimized_experience.data.reliability import load_reliability_profile
from optimized_experience.data.ride_durations import load_ride_duration_map
from optimized_experience.data.shows import load_show_category_map
from optimized_experience.optimizer.contracts import (
    LightningLaneType,
    NodeKind,
    Objective,
    Plan,
    ShowCategory,
    TimeWindow,
)
from optimized_experience.planning import PARK_TIMEZONE, build_listing_nodes

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Optimized Disneyland Experience API",
    description="Live Disneyland single-day itinerary optimizer -- greedy heuristic and OR-Tools routing search.",
)

_default_origins = "http://localhost:3000"
_cors_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", _default_origins).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Built once at import time (server startup), reused for the process
# lifetime -- see module docstring.
_data_source, _weather_source = build_sources(replay_dir=None)

_OBJECTIVE_BY_QUERY_VALUE: dict[str, Objective] = {
    "maximize_prize": "MAXIMIZE_PRIZE",
    "all_rides_challenge": "ALL_RIDES_CHALLENGE",
}


class PlanResponse(BaseModel):
    generated_at: datetime
    plan: Plan


class AttractionListing(BaseModel):
    """One row for the onboarding picker / swap list / build-your-own picker --
    a deliberately slim view of Node: no base_prize, mandatory, or raw
    wait_forecast, since those are solver-internal and this endpoint feeds UI
    that should never need to know the solver exists."""

    id: str
    name: str
    kind: NodeKind
    land: str | None
    show_category: ShowCategory | None
    wait_minutes: float
    duration_minutes: float
    lightning_lane_type: LightningLaneType
    lightning_lane_window: TimeWindow | None
    lightning_lane_price: PriceInfo | None
    # For kind == "SHOW": the specific showtimes it actually runs at (a parade
    # doesn't run continuously) -- lets the frontend's manual-schedule view flag
    # a slot that falls outside any of them. For kind == "ATTRACTION" this is
    # just wide operating hours, not meaningfully constraining.
    time_windows: list[TimeWindow]


class AttractionsResponse(BaseModel):
    generated_at: datetime
    attractions: list[AttractionListing]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/plan", response_model=PlanResponse)
def post_plan(
    preferences: Preferences,
    objective: str = Query("maximize_prize", pattern="^(maximize_prize|all_rides_challenge)$"),
) -> PlanResponse:
    reliability_profile = load_reliability_profile(DEFAULT_CONFIG_DIR / "reliability_profile.yaml")
    land_map = load_land_map(DEFAULT_CONFIG_DIR / "land_map.yaml")
    ride_duration_map = load_ride_duration_map(DEFAULT_CONFIG_DIR / "ride_durations.yaml")
    show_category_map = load_show_category_map(DEFAULT_CONFIG_DIR / "show_categories.yaml")

    try:
        plan, start_time = generate_plan(
            _OBJECTIVE_BY_QUERY_VALUE[objective],
            _data_source,
            _weather_source,
            preferences,
            reliability_profile,
            start_time_override=None,
            is_replay=False,
            land_map=land_map,
            ride_duration_map=ride_duration_map,
            show_category_map=show_category_map,
            solver_name="ortools",
        )
    except httpx.HTTPError as exc:
        logger.exception("Upstream data source failed")
        raise HTTPException(status_code=502, detail=f"Upstream park/weather data unavailable: {exc}") from exc

    return PlanResponse(generated_at=start_time, plan=plan)


@app.get("/api/attractions", response_model=AttractionsResponse)
def get_attractions() -> AttractionsResponse:
    reliability_profile = load_reliability_profile(DEFAULT_CONFIG_DIR / "reliability_profile.yaml")
    land_map = load_land_map(DEFAULT_CONFIG_DIR / "land_map.yaml")
    ride_duration_map = load_ride_duration_map(DEFAULT_CONFIG_DIR / "ride_durations.yaml")
    show_category_map = load_show_category_map(DEFAULT_CONFIG_DIR / "show_categories.yaml")

    try:
        children = _data_source.get_children()
        live = _data_source.get_live()
    except httpx.HTTPError as exc:
        logger.exception("Upstream data source failed")
        raise HTTPException(status_code=502, detail=f"Upstream park data unavailable: {exc}") from exc

    nodes = build_listing_nodes(children, live, reliability_profile, land_map, ride_duration_map, show_category_map)
    attractions = [
        AttractionListing(
            id=node.id,
            name=node.name,
            kind=node.kind,
            land=node.land,
            show_category=node.show_category,
            wait_minutes=node.wait_estimate_minutes,
            duration_minutes=node.service_time_minutes,
            lightning_lane_type=node.lightning_lane_type,
            lightning_lane_window=node.lightning_lane_window,
            lightning_lane_price=node.lightning_lane_price,
            time_windows=node.time_windows,
        )
        for node in nodes
    ]
    return AttractionsResponse(generated_at=datetime.now(PARK_TIMEZONE), attractions=attractions)
