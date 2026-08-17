"""Phase-1 entrypoint: fetch live park + weather data (or replay fixtures),
build a PlanRequest, solve it, and print a readable itinerary.

Headline behavior: generate the full day's plan once, up front (at/near park
open) -- see --watch for the rolling re-optimization loop that keeps it
fresh afterward, full recompute per tick rather than incremental patching.
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

from optimized_experience.data.client import DataSource, ReplayDataSource, ThemeParksWikiSource
from optimized_experience.data.lands import LandMap, load_land_map
from optimized_experience.data.preferences import Preferences, load_preferences
from optimized_experience.data.reliability import ReliabilityProfile, load_reliability_profile
from optimized_experience.data.ride_durations import RideDurationMap, load_ride_duration_map
from optimized_experience.data.shows import ShowCategoryMap, load_show_category_map
from optimized_experience.data.weather_client import NWSWeatherSource, ReplayWeatherSource, WeatherSource
from optimized_experience.optimizer.contracts import NavigationStrategy, Objective, Plan
from optimized_experience.optimizer.factory import SolverName, get_solver
from optimized_experience.optimizer.rationale import annotate_guest_rationale
from optimized_experience.planning import (
    build_activity_nodes,
    build_candidate_nodes,
    build_plan_request,
    resolve_park_close,
    resolve_start_time,
)

NAVIGATION_STRATEGIES: list[NavigationStrategy] = ["TIME_OPTIMAL", "LAND_ORDER", "CLUSTERED"]

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
WATCH_INTERVAL_SECONDS = 120  # matches themeparks.wiki's live refresh cadence


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Disneyland single-day itinerary optimizer (phase 1: greedy baseline)."
    )
    parser.add_argument(
        "--replay",
        type=Path,
        default=None,
        help=(
            "Path to a fixture directory (children.json, live.json, schedule.json, "
            "weather_hourly.json) for offline demos/tests. Omit for live mode."
        ),
    )
    parser.add_argument(
        "--mode", choices=["maximize_prize", "all_rides_challenge"], default="maximize_prize"
    )
    parser.add_argument("--preferences", type=Path, default=DEFAULT_CONFIG_DIR / "preferences.yaml")
    parser.add_argument(
        "--reliability-profile", type=Path, default=DEFAULT_CONFIG_DIR / "reliability_profile.yaml"
    )
    parser.add_argument("--land-map", type=Path, default=DEFAULT_CONFIG_DIR / "land_map.yaml")
    parser.add_argument(
        "--ride-durations", type=Path, default=DEFAULT_CONFIG_DIR / "ride_durations.yaml"
    )
    parser.add_argument(
        "--show-categories", type=Path, default=DEFAULT_CONFIG_DIR / "show_categories.yaml"
    )
    parser.add_argument(
        "--solver",
        choices=["greedy", "ortools", "compare"],
        default="greedy",
        help="greedy = fast myopic heuristic. ortools = global routing search over real "
        "travel time, provably-near-optimal but with documented simplifications (see "
        "ortools_solver.py) -- Lightning Lane's book/redeem two-step collapses into one "
        "visit, and prize/wait are computed once per node rather than dynamically. "
        "'compare' solves with both and prints both.",
    )
    parser.add_argument(
        "--navigation",
        choices=["time_optimal", "land_order", "clustered", "compare"],
        default=None,
        help="Override preferences.yaml's navigation_strategy for this run. 'compare' solves "
        "the same day under all three strategies and prints all three so you can compare "
        "(land_order requires preferences.yaml's land_order to be set).",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Re-fetch data and reprint the itinerary every ~2 minutes. Also reloads "
        "--preferences/--reliability-profile each tick, so editing those files between "
        "ticks (e.g. flipping use_lightning_lane) takes effect without restarting.",
    )
    parser.add_argument(
        "--no-lightning-lane",
        action="store_true",
        help="One-off override: plan the day with no Lightning Lane, regardless of what "
        "preferences.yaml says.",
    )
    parser.add_argument(
        "--start-time",
        type=str,
        default=None,
        help="ISO datetime to plan from, overriding everything else including "
        "preferences.yaml's planned_arrival. Default: preferences.yaml's planned_arrival if "
        "set (never earlier than official park opening); otherwise replay mode uses the "
        "fixture's opening time and live mode uses now (or park open, if not yet open).",
    )
    return parser


def build_sources(replay_dir: Path | None) -> tuple[DataSource, WeatherSource]:
    if replay_dir is not None:
        return ReplayDataSource(replay_dir), ReplayWeatherSource(replay_dir / "weather_hourly.json")
    return ThemeParksWikiSource(), NWSWeatherSource()


def load_current_preferences(args: argparse.Namespace, navigation_override: str | None = None) -> Preferences:
    preferences = load_preferences(args.preferences)
    updates: dict[str, object] = {}
    if args.no_lightning_lane:
        updates["use_lightning_lane"] = False
    nav = navigation_override or (args.navigation if args.navigation != "compare" else None)
    if nav:
        updates["navigation_strategy"] = nav.upper()
    if updates:
        preferences = preferences.model_copy(update=updates)
    return preferences


def generate_plan(
    objective: Objective,
    data_source: DataSource,
    weather_source: WeatherSource,
    preferences: Preferences,
    reliability_profile: ReliabilityProfile,
    start_time_override: str | None,
    is_replay: bool,
    land_map: LandMap | None = None,
    ride_duration_map: RideDurationMap | None = None,
    show_category_map: ShowCategoryMap | None = None,
    solver_name: SolverName = "greedy",
) -> tuple[Plan, datetime]:
    children = data_source.get_children()
    live = data_source.get_live()
    schedule = data_source.get_schedule()
    hourly_forecast = weather_source.get_hourly_forecast()

    start_time = (
        datetime.fromisoformat(start_time_override)
        if start_time_override
        else resolve_start_time(schedule, is_replay=is_replay, planned_arrival=preferences.planned_arrival)
    )
    park_close = resolve_park_close(schedule, start_time, preferences.planned_departure)

    candidate_nodes = build_candidate_nodes(
        children, live, preferences, reliability_profile, objective, land_map,
        ride_duration_map, show_category_map,
    )
    candidate_nodes += build_activity_nodes(preferences.activity_blocks, start_time, park_close)
    plan_request = build_plan_request(
        objective, start_time, park_close, candidate_nodes, hourly_forecast, preferences
    )
    plan = get_solver(objective, solver_name).solve(plan_request)
    plan = annotate_guest_rationale(plan, plan_request)
    return plan, start_time


def print_plan(plan: Plan, start_time: datetime) -> None:
    print(
        f"\nItinerary generated at {start_time.strftime('%Y-%m-%d %-I:%M %p')} "
        f"({plan.solver_name})"
    )
    print("=" * 72)
    for i, step in enumerate(plan.steps, start=1):
        print(f"{i:>2}. {step.planned_arrival.strftime('%-I:%M %p'):>8}  {step.action:<22} {step.node_name}")
        print(f"      {step.rationale}")
    print("-" * 72)
    print(f"Total prize collected: {plan.total_prize:.1f}")
    if plan.unscheduled_node_ids:
        print(f"Unscheduled ({len(plan.unscheduled_node_ids)}): {', '.join(plan.unscheduled_node_ids)}")
    if plan.unscheduled_mandatory_node_ids:
        print(
            f"\n*** WARNING: could not fit {len(plan.unscheduled_mandatory_node_ids)} mandatory "
            f"block(s) into today's plan: {', '.join(plan.unscheduled_mandatory_node_ids)} ***"
        )
    print(f"\n{plan.disclaimer}\n")


def main(argv: list[str] | None = None) -> None:
    args = _build_arg_parser().parse_args(argv)

    objective: Objective = "MAXIMIZE_PRIZE" if args.mode == "maximize_prize" else "ALL_RIDES_CHALLENGE"
    data_source, weather_source = build_sources(args.replay)

    solver_names: list[SolverName] = ["greedy", "ortools"] if args.solver == "compare" else [args.solver]
    nav_strategies: list[str | None] = (
        list(NAVIGATION_STRATEGIES) if args.navigation == "compare" else [None]
    )
    multi_combo = len(solver_names) > 1 or len(nav_strategies) > 1

    try:
        while True:
            # Reloaded every tick (not just once before the loop) so a guest editing
            # preferences.yaml mid-day -- e.g. turning Lightning Lane off -- takes
            # effect on the next re-plan without restarting the process.
            reliability_profile = load_reliability_profile(args.reliability_profile)
            land_map = load_land_map(args.land_map)
            ride_duration_map = load_ride_duration_map(args.ride_durations)
            show_category_map = load_show_category_map(args.show_categories)

            for solver_name in solver_names:
                for nav in nav_strategies:
                    preferences = load_current_preferences(args, navigation_override=nav)
                    plan, start_time = generate_plan(
                        objective, data_source, weather_source, preferences, reliability_profile,
                        args.start_time, is_replay=args.replay is not None, land_map=land_map,
                        ride_duration_map=ride_duration_map, show_category_map=show_category_map,
                        solver_name=solver_name,
                    )
                    if multi_combo:
                        label = " / ".join(
                            part for part in (solver_name if len(solver_names) > 1 else None,
                                               nav if len(nav_strategies) > 1 else None)
                            if part
                        )
                        print(f"\n\n{'#' * 20} {label} {'#' * 20}")
                    print_plan(plan, start_time)

            if not args.watch:
                break
            print(f"(re-planning again in {WATCH_INTERVAL_SECONDS}s -- Ctrl+C to stop)")
            time.sleep(WATCH_INTERVAL_SECONDS)
    finally:
        close = getattr(data_source, "close", None)
        if close:
            close()
        close = getattr(weather_source, "close", None)
        if close:
            close()


if __name__ == "__main__":
    main()
