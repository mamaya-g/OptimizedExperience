from datetime import datetime
from pathlib import Path

import pytest

from optimized_experience.data.client import ReplayDataSource
from optimized_experience.data.preferences import ActivityBlock, BlockPlacement, Preferences
from optimized_experience.data.reliability import ReliabilityProfile
from optimized_experience.optimizer.contracts import TimeWindow
from optimized_experience.data.models import ScheduleEntry, ScheduleResponse
from optimized_experience.planning import (
    build_activity_nodes,
    build_candidate_nodes,
    build_plan_request,
    resolve_park_close,
    resolve_start_time,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "disneyland_aug16"
DAY_START = datetime(2026, 8, 16, 9, 0)
DAY_END = datetime(2026, 8, 16, 22, 0)

_SCHEDULE = ScheduleResponse(
    id="park",
    timezone="America/Los_Angeles",
    schedule=[
        ScheduleEntry(
            date="2026-08-16",
            type="OPERATING",
            openingTime=datetime(2026, 8, 16, 8, 0),
            closingTime=datetime(2026, 8, 16, 22, 0),
        )
    ],
)


def _load_children_and_live():
    source = ReplayDataSource(FIXTURE_DIR)
    return source.get_children(), source.get_live()


def test_lightning_lane_present_by_default():
    children, live = _load_children_and_live()
    nodes = build_candidate_nodes(children, live, Preferences(), ReliabilityProfile(), "MAXIMIZE_PRIZE")
    assert any(n.lightning_lane_type != "NONE" for n in nodes)


def test_lightning_lane_disabled_when_use_lightning_lane_is_false():
    children, live = _load_children_and_live()
    preferences = Preferences(use_lightning_lane=False)
    nodes = build_candidate_nodes(children, live, preferences, ReliabilityProfile(), "MAXIMIZE_PRIZE")
    assert all(n.lightning_lane_type == "NONE" for n in nodes)
    assert all(n.lightning_lane_window is None for n in nodes)


def test_lightning_lane_disabled_in_challenge_mode_too():
    children, live = _load_children_and_live()
    preferences = Preferences(use_lightning_lane=False)
    nodes = build_candidate_nodes(children, live, preferences, ReliabilityProfile(), "ALL_RIDES_CHALLENGE")
    assert all(n.lightning_lane_type == "NONE" for n in nodes)


def test_build_activity_nodes_preferred_range():
    block = ActivityBlock(
        name="Lunch", duration_minutes=45, placement=BlockPlacement.PREFERRED_RANGE,
        range_start=datetime(2026, 8, 16, 12, 0), range_end=datetime(2026, 8, 16, 13, 30),
    )
    nodes = build_activity_nodes([block], DAY_START, DAY_END)
    assert len(nodes) == 1
    node = nodes[0]
    assert node.kind == "ACTIVITY" and node.mandatory
    assert node.time_windows == [TimeWindow(start=block.range_start, end=block.range_end)]
    assert node.service_time_minutes == 45


def test_build_activity_nodes_fixed_time():
    block = ActivityBlock(
        name="Dinner Reservation", duration_minutes=60, placement=BlockPlacement.FIXED_TIME,
        fixed_time=datetime(2026, 8, 16, 18, 0),
    )
    nodes = build_activity_nodes([block], DAY_START, DAY_END)
    window = nodes[0].time_windows[0]
    assert window.start == datetime(2026, 8, 16, 18, 0)
    assert window.end == datetime(2026, 8, 16, 19, 0)


def test_build_activity_nodes_solver_choice_spans_whole_day_for_generic_kind():
    block = ActivityBlock(name="Shopping", duration_minutes=30, placement=BlockPlacement.SOLVER_CHOICE)
    nodes = build_activity_nodes([block], DAY_START, DAY_END)
    window = nodes[0].time_windows[0]
    assert window.start == DAY_START
    assert window.end == DAY_END


def test_build_activity_nodes_solver_choice_dinner_defaults_to_evening_not_park_open():
    # Regression: a mandatory block's forcing prize dominates scoring so
    # completely that, without a kind-aware default window, "Dinner" would
    # get grabbed at park open (the first opportunity) instead of at dinner
    # time -- defeats the point of calling it dinner.
    from optimized_experience.data.preferences import ActivityKind

    block = ActivityBlock(
        name="Dinner", duration_minutes=60, placement=BlockPlacement.SOLVER_CHOICE, kind=ActivityKind.DINNER
    )
    nodes = build_activity_nodes([block], DAY_START, DAY_END)
    window = nodes[0].time_windows[0]
    assert window.start == datetime(2026, 8, 16, 17, 0)
    assert window.end == datetime(2026, 8, 16, 20, 30)
    assert window.start > DAY_START  # not park open


def test_build_activity_nodes_solver_choice_falls_back_when_default_window_infeasible():
    from optimized_experience.data.preferences import ActivityKind

    # Guest leaves at 3pm -- the default dinner window (5-8:30pm) can't fit.
    early_day_end = datetime(2026, 8, 16, 15, 0)
    block = ActivityBlock(
        name="Dinner", duration_minutes=60, placement=BlockPlacement.SOLVER_CHOICE, kind=ActivityKind.DINNER
    )
    nodes = build_activity_nodes([block], DAY_START, early_day_end)
    window = nodes[0].time_windows[0]
    assert window.start == DAY_START
    assert window.end == early_day_end


def test_resolve_park_close_earlier_departure_tightens_budget():
    departure = datetime(2026, 8, 16, 19, 0)  # earlier than official 10pm close
    result = resolve_park_close(_SCHEDULE, DAY_START, departure)
    assert result == departure


def test_resolve_park_close_later_departure_is_ignored():
    later_departure = datetime(2026, 8, 16, 23, 30)  # later than official 10pm close
    result = resolve_park_close(_SCHEDULE, DAY_START, later_departure)
    assert result == datetime(2026, 8, 16, 22, 0)  # official closing wins


def test_resolve_park_close_no_departure_uses_official_closing():
    result = resolve_park_close(_SCHEDULE, DAY_START, None)
    assert result == datetime(2026, 8, 16, 22, 0)


def test_resolve_start_time_replay_uses_fixture_opening():
    result = resolve_start_time(_SCHEDULE, is_replay=True)
    assert result == datetime(2026, 8, 16, 8, 0)


def test_resolve_start_time_planned_arrival_after_opening_is_honored():
    arrival = datetime(2026, 8, 16, 10, 30)
    result = resolve_start_time(_SCHEDULE, is_replay=True, planned_arrival=arrival)
    assert result == arrival


def test_resolve_start_time_planned_arrival_before_opening_is_clamped():
    too_early = datetime(2026, 8, 16, 6, 0)  # park opens at 8am
    result = resolve_start_time(_SCHEDULE, is_replay=True, planned_arrival=too_early)
    assert result == datetime(2026, 8, 16, 8, 0)  # can't enter before opening


def test_resolve_start_time_live_mode_uses_now_when_park_already_open():
    now = datetime(2026, 8, 16, 11, 0)
    result = resolve_start_time(_SCHEDULE, is_replay=False, now=now)
    assert result == now


def test_resolve_start_time_live_mode_clamps_to_opening_before_park_opens():
    now = datetime(2026, 8, 16, 6, 0)  # before 8am opening
    result = resolve_start_time(_SCHEDULE, is_replay=False, now=now)
    assert result == datetime(2026, 8, 16, 8, 0)


def test_build_plan_request_resolves_navigation_fields_from_enum_preferences():
    # Regression: str(SomeStrEnum.MEMBER) returns "ClassName.MEMBER", not the
    # plain value, even though it's a str subclass -- caught this building
    # walking_pace_mph/navigation_strategy resolution.
    preferences = Preferences(walking_pace="FAST", navigation_strategy="CLUSTERED")
    request = build_plan_request("MAXIMIZE_PRIZE", DAY_START, DAY_END, [], [], preferences)
    assert request.navigation_strategy == "CLUSTERED"
    assert request.walking_pace_mph == pytest.approx(3.3)


def test_build_plan_request_resolves_navigation_fields_from_raw_string_preferences():
    # preferences.model_copy(update=...) (used by the CLI's --navigation override)
    # sets a raw str, not a re-validated Enum member -- must also work.
    preferences = Preferences().model_copy(
        update={"walking_pace": "SLOW", "navigation_strategy": "LAND_ORDER"}
    )
    request = build_plan_request("MAXIMIZE_PRIZE", DAY_START, DAY_END, [], [], preferences)
    assert request.navigation_strategy == "LAND_ORDER"
    assert request.walking_pace_mph == pytest.approx(2.0)
