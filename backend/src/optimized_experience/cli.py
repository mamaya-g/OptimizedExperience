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
from zoneinfo import ZoneInfo

from optimized_experience.data.client import DataSource, ReplayDataSource, ThemeParksWikiSource
from optimized_experience.data.models import ScheduleResponse
from optimized_experience.data.preferences import Preferences, load_preferences
from optimized_experience.data.reliability import ReliabilityProfile, load_reliability_profile
from optimized_experience.data.weather_client import NWSWeatherSource, ReplayWeatherSource, WeatherSource
from optimized_experience.optimizer.contracts import Objective, Plan
from optimized_experience.optimizer.factory import get_solver
from optimized_experience.planning import build_candidate_nodes, build_plan_request, opening_time_for

PARK_TIMEZONE = ZoneInfo("America/Los_Angeles")
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
    parser.add_argument(
        "--watch", action="store_true", help="Re-fetch data and reprint the itinerary every ~2 minutes."
    )
    parser.add_argument(
        "--start-time",
        type=str,
        default=None,
        help="ISO datetime to plan from. Default: replay mode uses the fixture's opening time; "
        "live mode uses now (or park open, if the park hasn't opened yet).",
    )
    return parser


def build_sources(replay_dir: Path | None) -> tuple[DataSource, WeatherSource]:
    if replay_dir is not None:
        return ReplayDataSource(replay_dir), ReplayWeatherSource(replay_dir / "weather_hourly.json")
    return ThemeParksWikiSource(), NWSWeatherSource()


def _default_start_time(schedule: ScheduleResponse, is_replay: bool) -> datetime:
    if is_replay:
        first_entry = schedule.schedule[0]
        if first_entry.openingTime is None:
            raise ValueError("Replay schedule fixture has no opening time for its first entry.")
        return first_entry.openingTime
    now = datetime.now(PARK_TIMEZONE)
    opening = opening_time_for(schedule, now)
    if opening is not None and now < opening:
        return opening
    return now


def _resolve_start_time(args: argparse.Namespace, schedule: ScheduleResponse) -> datetime:
    if args.start_time:
        return datetime.fromisoformat(args.start_time)
    return _default_start_time(schedule, is_replay=args.replay is not None)


def generate_plan(
    objective: Objective,
    data_source: DataSource,
    weather_source: WeatherSource,
    preferences: Preferences,
    reliability_profile: ReliabilityProfile,
    start_time_override: str | None,
    is_replay: bool,
) -> tuple[Plan, datetime]:
    children = data_source.get_children()
    live = data_source.get_live()
    schedule = data_source.get_schedule()
    hourly_forecast = weather_source.get_hourly_forecast()

    start_time = (
        datetime.fromisoformat(start_time_override)
        if start_time_override
        else _default_start_time(schedule, is_replay=is_replay)
    )

    candidate_nodes = build_candidate_nodes(children, live, preferences, reliability_profile, objective)
    plan_request = build_plan_request(
        objective, start_time, schedule, candidate_nodes, hourly_forecast, preferences
    )
    plan = get_solver(objective).solve(plan_request)
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
    print(f"\n{plan.disclaimer}\n")


def main(argv: list[str] | None = None) -> None:
    args = _build_arg_parser().parse_args(argv)

    objective: Objective = "MAXIMIZE_PRIZE" if args.mode == "maximize_prize" else "ALL_RIDES_CHALLENGE"
    data_source, weather_source = build_sources(args.replay)
    preferences = load_preferences(args.preferences)
    reliability_profile = load_reliability_profile(args.reliability_profile)

    try:
        while True:
            plan, start_time = generate_plan(
                objective,
                data_source,
                weather_source,
                preferences,
                reliability_profile,
                args.start_time,
                is_replay=args.replay is not None,
            )
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
