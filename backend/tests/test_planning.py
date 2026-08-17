from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from optimized_experience.data.client import ReplayDataSource
from optimized_experience.data.preferences import ActivityBlock, BlockPlacement, Preferences
from optimized_experience.data.reliability import ReliabilityProfile
from optimized_experience.data.ride_durations import load_ride_duration_map
from optimized_experience.data.shows import load_show_category_map
from optimized_experience.optimizer.contracts import TimeWindow
from optimized_experience.data.models import (
    ChildEntity,
    ChildrenResponse,
    LiveDataEntry,
    LiveResponse,
    ScheduleEntry,
    ScheduleResponse,
    Showtime,
)
from optimized_experience.planning import (
    MANDATORY_ACTIVITY_PRIZE,
    build_activity_nodes,
    build_candidate_nodes,
    build_listing_nodes,
    build_plan_request,
    resolve_park_close,
    resolve_start_time,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "disneyland_aug16"
CONFIG_DIR = Path(__file__).parent.parent / "config"
DAY_START = datetime(2026, 8, 16, 9, 0)
DAY_END = datetime(2026, 8, 16, 22, 0)

RIDE_DURATION_MAP = load_ride_duration_map(CONFIG_DIR / "ride_durations.example.yaml")
SHOW_CATEGORY_MAP = load_show_category_map(CONFIG_DIR / "show_categories.example.yaml")

# Real ids/slugs present in the disneyland_aug16 fixture, cross-referenced against
# show_categories.example.yaml -- Paint the Night is OPERATING with showtimes there,
# and is the PARADE-categorized show that fixture actually has live.
PAINT_THE_NIGHT_ID = "c60e9de0-df2b-4484-9b05-299939dc247a"
WONDROUS_JOURNEYS_FIREWORKS_ID = "115863ac-0880-4630-afd3-b1a1b5033d51"
RISE_OF_THE_RESISTANCE_ID = "34b1d70f-11c4-42df-935e-d5582c9f1a8e"
SPACE_MOUNTAIN_ID = "9167db1d-e5e7-46da-a07f-ae30a87bc4c4"

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
    assert window.end == DAY_END  # dinner bound (5-11pm) capped by park close (10pm)
    assert window.start > DAY_START  # not park open


def test_build_activity_nodes_solver_choice_falls_back_when_default_window_infeasible():
    from optimized_experience.data.preferences import ActivityKind

    # Guest leaves at 3pm -- the default dinner window (5-11pm) can't fit.
    early_day_end = datetime(2026, 8, 16, 15, 0)
    block = ActivityBlock(
        name="Dinner", duration_minutes=60, placement=BlockPlacement.SOLVER_CHOICE, kind=ActivityKind.DINNER
    )
    nodes = build_activity_nodes([block], DAY_START, early_day_end)
    window = nodes[0].time_windows[0]
    assert window.start == DAY_START
    assert window.end == early_day_end


def test_build_activity_nodes_clamps_preferred_range_lunch_outside_allowed_hours():
    # A guest requesting "lunch" at 9-10am (outside the 11am-3pm bound) gets
    # clamped into the allowed window rather than honored literally.
    from optimized_experience.data.preferences import ActivityKind

    block = ActivityBlock(
        name="Lunch", duration_minutes=45, placement=BlockPlacement.PREFERRED_RANGE, kind=ActivityKind.LUNCH,
        range_start=datetime(2026, 8, 16, 9, 0), range_end=datetime(2026, 8, 16, 10, 0),
    )
    nodes = build_activity_nodes([block], DAY_START, DAY_END)
    window = nodes[0].time_windows[0]
    assert window.start == datetime(2026, 8, 16, 11, 0)
    assert window.end == datetime(2026, 8, 16, 15, 0)


def test_build_activity_nodes_clamps_fixed_time_dinner_outside_allowed_hours():
    # A dinner reservation fixed at 2am gets clamped into the 5-11pm bound.
    from optimized_experience.data.preferences import ActivityKind

    block = ActivityBlock(
        name="Dinner", duration_minutes=60, placement=BlockPlacement.FIXED_TIME, kind=ActivityKind.DINNER,
        fixed_time=datetime(2026, 8, 16, 2, 0),
    )
    nodes = build_activity_nodes([block], DAY_START, DAY_END)
    window = nodes[0].time_windows[0]
    assert window.start == datetime(2026, 8, 16, 17, 0)
    assert window.end == DAY_END


def test_build_activity_nodes_partially_overlapping_preferred_range_lunch_is_tightened_not_replaced():
    # A guest range that partially overlaps the bound (10:30-11:30) should be
    # tightened to the overlap, not blown away entirely.
    from optimized_experience.data.preferences import ActivityKind

    block = ActivityBlock(
        name="Lunch", duration_minutes=45, placement=BlockPlacement.PREFERRED_RANGE, kind=ActivityKind.LUNCH,
        range_start=datetime(2026, 8, 16, 10, 30), range_end=datetime(2026, 8, 16, 11, 30),
    )
    nodes = build_activity_nodes([block], DAY_START, DAY_END)
    window = nodes[0].time_windows[0]
    assert window.start == datetime(2026, 8, 16, 11, 0)
    assert window.end == datetime(2026, 8, 16, 11, 30)


def test_build_activity_nodes_snack_is_unconstrained_by_meal_hours():
    from optimized_experience.data.preferences import ActivityKind

    block = ActivityBlock(
        name="Snack", duration_minutes=15, placement=BlockPlacement.PREFERRED_RANGE, kind=ActivityKind.SNACK,
        range_start=datetime(2026, 8, 16, 9, 0), range_end=datetime(2026, 8, 16, 9, 15),
    )
    nodes = build_activity_nodes([block], DAY_START, DAY_END)
    window = nodes[0].time_windows[0]
    assert window.start == datetime(2026, 8, 16, 9, 0)
    assert window.end == datetime(2026, 8, 16, 9, 15)


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


def test_build_candidate_nodes_uses_real_ride_duration_not_flat_default():
    children, live = _load_children_and_live()
    nodes = build_candidate_nodes(
        children, live, Preferences(), ReliabilityProfile(), "MAXIMIZE_PRIZE",
        ride_duration_map=RIDE_DURATION_MAP,
    )
    rise = next(n for n in nodes if n.id == RISE_OF_THE_RESISTANCE_ID)
    assert rise.service_time_minutes == 18


def test_build_candidate_nodes_carries_lightning_lane_single_pass_price():
    children, live = _load_children_and_live()
    nodes = build_candidate_nodes(children, live, Preferences(), ReliabilityProfile(), "MAXIMIZE_PRIZE")
    rise = next(n for n in nodes if n.id == RISE_OF_THE_RESISTANCE_ID)
    assert rise.lightning_lane_type == "SINGLE"
    assert rise.lightning_lane_price is not None
    assert rise.lightning_lane_price.formatted == "$29.00"


def test_build_candidate_nodes_marks_must_go_show_mandatory():
    children, live = _load_children_and_live()
    preferences = Preferences(tiers={PAINT_THE_NIGHT_ID: "MUST_GO"})
    nodes = build_candidate_nodes(
        children, live, preferences, ReliabilityProfile(), "MAXIMIZE_PRIZE",
        show_category_map=SHOW_CATEGORY_MAP,
    )
    paint_the_night = next(n for n in nodes if n.id == PAINT_THE_NIGHT_ID)
    assert paint_the_night.mandatory is True
    assert paint_the_night.base_prize == MANDATORY_ACTIVITY_PRIZE
    assert paint_the_night.show_category == "PARADE"


def test_build_candidate_nodes_does_not_force_show_when_not_tagged():
    children, live = _load_children_and_live()
    nodes = build_candidate_nodes(
        children, live, Preferences(), ReliabilityProfile(), "MAXIMIZE_PRIZE",
        show_category_map=SHOW_CATEGORY_MAP,
    )
    paint_the_night = next(n for n in nodes if n.id == PAINT_THE_NIGHT_ID)
    assert paint_the_night.mandatory is False
    assert paint_the_night.base_prize != MANDATORY_ACTIVITY_PRIZE


def test_build_candidate_nodes_nice_to_have_show_is_included_but_not_mandatory():
    children, live = _load_children_and_live()
    preferences = Preferences(tiers={WONDROUS_JOURNEYS_FIREWORKS_ID: "NICE_TO_HAVE"})
    nodes = build_candidate_nodes(
        children, live, preferences, ReliabilityProfile(), "MAXIMIZE_PRIZE",
        show_category_map=SHOW_CATEGORY_MAP,
    )
    wondrous = next(n for n in nodes if n.id == WONDROUS_JOURNEYS_FIREWORKS_ID)
    assert wondrous.mandatory is False
    assert wondrous.base_prize == 40.0


def test_build_candidate_nodes_multiple_must_go_shows_all_mandatory():
    # Regression: a single-pick "one specific show" mechanism used to make
    # this impossible. A day can run several shows a guest wants to see (e.g.
    # a parade AND a nighttime spectacular), and any number should be able to
    # be tagged must-see, not just one per category.
    children, live = _load_children_and_live()
    preferences = Preferences(
        tiers={PAINT_THE_NIGHT_ID: "MUST_GO", WONDROUS_JOURNEYS_FIREWORKS_ID: "MUST_GO"}
    )
    nodes = build_candidate_nodes(
        children, live, preferences, ReliabilityProfile(), "MAXIMIZE_PRIZE",
        show_category_map=SHOW_CATEGORY_MAP,
    )
    paint_the_night = next(n for n in nodes if n.id == PAINT_THE_NIGHT_ID)
    wondrous = next(n for n in nodes if n.id == WONDROUS_JOURNEYS_FIREWORKS_ID)
    assert paint_the_night.mandatory is True
    assert wondrous.mandatory is True


def test_build_candidate_nodes_must_go_show_does_not_force_other_shows_in_same_category():
    # A day can run several NIGHTTIME_SPECTACULAR shows at once (confirmed
    # live: Fantasmic!, Wondrous Journeys, Shadows of Memory, Fire of the
    # Rising Moons all categorized the same) -- tagging one must-see must not
    # drag every other show in its category along as mandatory too.
    children, live = _load_children_and_live()
    preferences = Preferences(tiers={WONDROUS_JOURNEYS_FIREWORKS_ID: "MUST_GO"})
    nodes = build_candidate_nodes(
        children, live, preferences, ReliabilityProfile(), "MAXIMIZE_PRIZE",
        show_category_map=SHOW_CATEGORY_MAP,
    )
    fantasmic = next((n for n in nodes if n.name == "Fantasmic!"), None)
    if fantasmic is not None:
        assert fantasmic.mandatory is False


def test_build_candidate_nodes_challenge_mode_still_includes_must_go_show():
    # ALL_RIDES_CHALLENGE otherwise excludes every SHOW entity outright -- a guest
    # explicitly tagging a show must-see should still get it forced in.
    children, live = _load_children_and_live()
    preferences = Preferences(tiers={PAINT_THE_NIGHT_ID: "MUST_GO"})
    nodes = build_candidate_nodes(
        children, live, preferences, ReliabilityProfile(), "ALL_RIDES_CHALLENGE",
        show_category_map=SHOW_CATEGORY_MAP,
    )
    assert any(n.id == PAINT_THE_NIGHT_ID for n in nodes)


def test_build_candidate_nodes_challenge_mode_includes_nice_to_have_show_but_not_mandatory():
    children, live = _load_children_and_live()
    preferences = Preferences(tiers={WONDROUS_JOURNEYS_FIREWORKS_ID: "NICE_TO_HAVE"})
    nodes = build_candidate_nodes(
        children, live, preferences, ReliabilityProfile(), "ALL_RIDES_CHALLENGE",
        show_category_map=SHOW_CATEGORY_MAP,
    )
    wondrous = next((n for n in nodes if n.id == WONDROUS_JOURNEYS_FIREWORKS_ID), None)
    assert wondrous is not None
    assert wondrous.mandatory is False


def test_build_candidate_nodes_challenge_mode_excludes_unrequested_shows():
    children, live = _load_children_and_live()
    nodes = build_candidate_nodes(
        children, live, Preferences(), ReliabilityProfile(), "ALL_RIDES_CHALLENGE",
        show_category_map=SHOW_CATEGORY_MAP,
    )
    assert all(n.kind != "SHOW" for n in nodes)


def test_build_candidate_nodes_repeat_counts_duplicates_node_with_suffixed_id():
    children, live = _load_children_and_live()
    preferences = Preferences(repeat_counts={"spacemountain": 3})
    nodes = build_candidate_nodes(children, live, preferences, ReliabilityProfile(), "MAXIMIZE_PRIZE")
    matches = [n for n in nodes if n.id == SPACE_MOUNTAIN_ID or n.id.startswith(f"{SPACE_MOUNTAIN_ID}-visit-")]
    assert {n.id for n in matches} == {
        SPACE_MOUNTAIN_ID, f"{SPACE_MOUNTAIN_ID}-visit-2", f"{SPACE_MOUNTAIN_ID}-visit-3"
    }


def test_build_candidate_nodes_repeat_counts_are_spread_across_non_overlapping_windows():
    # Regression: duplicate candidates used to share the same wide operating
    # window, so a travel-minimizing solver (zero cost between visits to the
    # same location) would happily schedule them back-to-back. Each repeat
    # visit must get its own slice of the day so that can't happen.
    children, live = _load_children_and_live()
    preferences = Preferences(repeat_counts={"spacemountain": 3})
    nodes = build_candidate_nodes(children, live, preferences, ReliabilityProfile(), "MAXIMIZE_PRIZE")
    matches = sorted(
        (n for n in nodes if n.id == SPACE_MOUNTAIN_ID or n.id.startswith(f"{SPACE_MOUNTAIN_ID}-visit-")),
        key=lambda n: n.time_windows[0].start,
    )
    assert len(matches) == 3
    for earlier, later in zip(matches, matches[1:]):
        assert earlier.time_windows[0].end <= later.time_windows[0].start


def test_build_candidate_nodes_repeat_count_of_one_does_not_duplicate():
    children, live = _load_children_and_live()
    preferences = Preferences(repeat_counts={"spacemountain": 1})
    nodes = build_candidate_nodes(children, live, preferences, ReliabilityProfile(), "MAXIMIZE_PRIZE")
    assert sum(1 for n in nodes if n.id.startswith(SPACE_MOUNTAIN_ID)) == 1


def test_build_listing_nodes_is_unfiltered_by_tier():
    children, live = _load_children_and_live()
    preferences = Preferences(tiers={"starwarsriseoftheresistance": "SKIP"})
    solvable = build_candidate_nodes(children, live, preferences, ReliabilityProfile(), "MAXIMIZE_PRIZE")
    listing = build_listing_nodes(children, live, ReliabilityProfile(), ride_duration_map=RIDE_DURATION_MAP)
    assert not any(n.id == RISE_OF_THE_RESISTANCE_ID for n in solvable)
    rise = next(n for n in listing if n.id == RISE_OF_THE_RESISTANCE_ID)
    assert rise.service_time_minutes == 18


def test_build_listing_nodes_includes_shows_and_attractions_regardless_of_mandatory_status():
    children, live = _load_children_and_live()
    listing = build_listing_nodes(children, live, ReliabilityProfile())
    assert any(n.id == PAINT_THE_NIGHT_ID for n in listing)
    assert all(not n.mandatory for n in listing)


def test_build_plan_request_resolves_navigation_fields_from_raw_string_preferences():
    # preferences.model_copy(update=...) (used by the CLI's --navigation override)
    # sets a raw str, not a re-validated Enum member -- must also work.
    preferences = Preferences().model_copy(
        update={"walking_pace": "SLOW", "navigation_strategy": "LAND_ORDER"}
    )
    request = build_plan_request("MAXIMIZE_PRIZE", DAY_START, DAY_END, [], [], preferences)
    assert request.navigation_strategy == "LAND_ORDER"
    assert request.walking_pace_mph == pytest.approx(2.0)


def test_build_activity_nodes_clamps_dinner_to_pacific_hours_when_day_start_is_utc_aware():
    # Regression: a guest-supplied planned_arrival/departure arrives from the
    # browser as a UTC ("Z"-suffixed) timestamp. day_start.replace(hour=17)
    # on a UTC-aware datetime used to set 5pm UTC (10am Pacific), not 5pm
    # Pacific -- "dinner" landed at 10am. day_start/day_end here represent
    # 9am-11pm Pacific, but expressed with UTC tzinfo, exactly like a real
    # request from the API.
    utc_day_start = datetime(2026, 8, 17, 16, 0, tzinfo=timezone.utc)  # 9am Pacific
    utc_day_end = datetime(2026, 8, 18, 6, 0, tzinfo=timezone.utc)  # 11pm Pacific
    block = ActivityBlock(name="Dinner", duration_minutes=60, placement=BlockPlacement.SOLVER_CHOICE, kind="DINNER")
    nodes = build_activity_nodes([block], utc_day_start, utc_day_end)
    window = nodes[0].time_windows[0]

    pacific = ZoneInfo("America/Los_Angeles")
    assert window.start.astimezone(pacific).hour == 17
    assert window.end.astimezone(pacific).hour == 23


def test_build_activity_nodes_clamps_preferred_range_dinner_to_pacific_hours_when_utc_aware():
    # Same regression as above, but for an explicit guest-picked time rather
    # than the SOLVER_CHOICE default window.
    utc_day_start = datetime(2026, 8, 17, 16, 0, tzinfo=timezone.utc)
    utc_day_end = datetime(2026, 8, 18, 6, 0, tzinfo=timezone.utc)
    # Guest picked "7:30 PM" Pacific for dinner -- sent as its correct UTC instant.
    range_start = datetime(2026, 8, 18, 2, 30, tzinfo=timezone.utc)  # 7:30pm Pacific
    range_end = datetime(2026, 8, 18, 3, 30, tzinfo=timezone.utc)  # 8:30pm Pacific
    block = ActivityBlock(
        name="Dinner", duration_minutes=60, placement=BlockPlacement.PREFERRED_RANGE, kind="DINNER",
        range_start=range_start, range_end=range_end,
    )
    nodes = build_activity_nodes([block], utc_day_start, utc_day_end)
    window = nodes[0].time_windows[0]

    pacific = ZoneInfo("America/Los_Angeles")
    assert window.start.astimezone(pacific).hour == 19
    assert window.start.astimezone(pacific).minute == 30
    assert window.end.astimezone(pacific).hour == 20


def _show_entry(entity_id: str, name: str, showtime: datetime, degenerate: bool = True) -> LiveDataEntry:
    return LiveDataEntry(
        id=entity_id,
        name=name,
        entityType="SHOW",
        status="OPERATING",
        showtimes=[Showtime(startTime=showtime, endTime=showtime if degenerate else showtime + timedelta(minutes=20))],
    )


def test_build_candidate_nodes_widens_degenerate_zero_width_showtime_window():
    # Regression: themeparks.wiki sometimes reports a showtime as a single
    # instant (startTime == endTime, observed live for Fantasmic!/Paint the
    # Night) rather than a real duration. A zero-width feasibility window is
    # all but unschedulable -- nothing will ever arrive at that exact instant
    # -- so it must be widened using the resolved service duration.
    showtime = datetime(2026, 8, 16, 21, 5)
    entry = _show_entry("fake-fantasmic-id", "Fantasmic!", showtime, degenerate=True)
    children = ChildrenResponse(
        id="park", name="park", entityType="PARK", timezone="America/Los_Angeles",
        children=[ChildEntity(id="fake-fantasmic-id", name="Fantasmic!", entityType="SHOW", slug="fantasmic")],
    )
    live = LiveResponse(id="park", liveData=[entry])
    preferences = Preferences(tiers={"fake-fantasmic-id": "MUST_GO"})

    nodes = build_candidate_nodes(
        children, live, preferences, ReliabilityProfile(), "MAXIMIZE_PRIZE",
        ride_duration_map=RIDE_DURATION_MAP, show_category_map=SHOW_CATEGORY_MAP,
    )
    node = next(n for n in nodes if n.id == "fake-fantasmic-id")
    window = node.time_windows[0]
    assert window.end > window.start
    assert node.service_time_minutes == 22  # hand-seeded Fantasmic! duration
    assert window.end - window.start == timedelta(minutes=22)
