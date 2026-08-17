#!/usr/bin/env python
"""Portfolio demo: runs both objective modes against the recorded Disneyland
fixture data and prints both itineraries. No live network access needed --
this is the "no live park visit required" verification path from the plan.

Run from backend/: PYTHONPATH=src .venv/bin/python scripts/demo_plan.py
"""

from __future__ import annotations

from pathlib import Path

from optimized_experience.cli import (
    DEFAULT_CONFIG_DIR,
    NAVIGATION_STRATEGIES,
    build_sources,
    generate_plan,
    print_plan,
)
from optimized_experience.data.lands import load_land_map
from optimized_experience.data.preferences import load_preferences
from optimized_experience.data.reliability import load_reliability_profile

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "disneyland_aug16"

MODES = [
    ("Maximize Prize", "MAXIMIZE_PRIZE"),
    ("All Rides Challenge", "ALL_RIDES_CHALLENGE"),
]


def main() -> None:
    preferences = load_preferences(DEFAULT_CONFIG_DIR / "preferences.yaml")
    reliability_profile = load_reliability_profile(DEFAULT_CONFIG_DIR / "reliability_profile.yaml")
    land_map = load_land_map(DEFAULT_CONFIG_DIR / "land_map.yaml")

    for label, objective in MODES:
        print(f"\n\n{'#' * 20} {label} {'#' * 20}")
        data_source, weather_source = build_sources(FIXTURE_DIR)
        plan, start_time = generate_plan(
            objective,
            data_source,
            weather_source,
            preferences,
            reliability_profile,
            start_time_override=None,
            is_replay=True,
            land_map=land_map,
        )
        print_plan(plan, start_time)

    # --navigation compare equivalent: same day, three navigation strategies,
    # solved and printed side by side so they can be compared directly.
    for strategy in NAVIGATION_STRATEGIES:
        strategy_preferences = preferences.model_copy(update={"navigation_strategy": strategy})
        print(f"\n\n{'#' * 20} MAXIMIZE_PRIZE / {strategy} {'#' * 20}")
        data_source, weather_source = build_sources(FIXTURE_DIR)
        plan, start_time = generate_plan(
            "MAXIMIZE_PRIZE",
            data_source,
            weather_source,
            strategy_preferences,
            reliability_profile,
            start_time_override=None,
            is_replay=True,
            land_map=land_map,
        )
        print_plan(plan, start_time)


if __name__ == "__main__":
    main()
