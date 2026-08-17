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

Preferences/reliability/land-map are reloaded from disk on every request
(cheap YAML parsing), matching --watch's per-tick reload -- editing
preferences.yaml takes effect on the next request without restarting the
server. Solver/objective are chosen per request via query params; all other
settings (tiers, activity blocks, navigation strategy, etc.) stay file-based,
matching the deliberately-viewer-only scope of the frontend for this round.
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
from optimized_experience.data.preferences import load_preferences
from optimized_experience.data.reliability import load_reliability_profile
from optimized_experience.optimizer.contracts import Objective, Plan

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Optimized Experience API",
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
    allow_methods=["GET"],
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/plan", response_model=PlanResponse)
def get_plan(
    objective: str = Query("maximize_prize", pattern="^(maximize_prize|all_rides_challenge)$"),
    solver: str = Query("greedy", pattern="^(greedy|ortools)$"),
) -> PlanResponse:
    preferences = load_preferences(DEFAULT_CONFIG_DIR / "preferences.yaml")
    reliability_profile = load_reliability_profile(DEFAULT_CONFIG_DIR / "reliability_profile.yaml")
    land_map = load_land_map(DEFAULT_CONFIG_DIR / "land_map.yaml")

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
            solver_name=solver,
        )
    except httpx.HTTPError as exc:
        logger.exception("Upstream data source failed")
        raise HTTPException(status_code=502, detail=f"Upstream park/weather data unavailable: {exc}") from exc

    return PlanResponse(generated_at=start_time, plan=plan)
