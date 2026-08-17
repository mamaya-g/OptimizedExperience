"""Bridges the data layer (live park data, weather, preferences, reliability)
into a PlanRequest the optimizer contract consumes. Kept separate from cli.py
so this orchestration logic is testable without going through argument
parsing.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from optimized_experience.data.lands import LandMap
from optimized_experience.data.models import (
    ChildEntity,
    ChildrenResponse,
    LiveDataEntry,
    LiveResponse,
    PriceInfo,
    ScheduleResponse,
)
from optimized_experience.data.preferences import (
    DEFAULT_BASE_PRIZE,
    ActivityBlock,
    ActivityKind,
    BlockPlacement,
    Preferences,
)
from optimized_experience.data.reliability import ReliabilityProfile
from optimized_experience.data.ride_durations import RideDurationMap
from optimized_experience.data.shows import ShowCategoryMap
from optimized_experience.data.weather_client import HourlyWeather
from optimized_experience.optimizer.contracts import (
    Coordinates,
    LightningLaneType,
    Node,
    Objective,
    PlanRequest,
    TimeWindow,
    WaitForecastEntry,
)
from optimized_experience.optimizer.geography import WALKING_PACE_MPH

PARK_TIMEZONE = ZoneInfo("America/Los_Angeles")


def resolve_start_time(
    schedule: ScheduleResponse,
    is_replay: bool,
    planned_arrival: datetime | None = None,
    now: datetime | None = None,
) -> datetime:
    """The moment the plan starts from. A guest-specified planned_arrival is
    honored but can never be earlier than the park's actual opening (can't
    enter before it opens). `now` is injectable for testability; defaults to
    the real current time in the park's timezone."""
    if is_replay:
        first_entry = schedule.schedule[0]
        if first_entry.openingTime is None:
            raise ValueError("Replay schedule fixture has no opening time for its first entry.")
        opening = first_entry.openingTime
        return max(planned_arrival, opening) if planned_arrival is not None else opening

    current = now if now is not None else datetime.now(PARK_TIMEZONE)
    opening = opening_time_for(schedule, current) or current
    if planned_arrival is not None:
        return max(planned_arrival, opening)
    return opening if current < opening else current


# A forcing constant, not a real preference weight: high enough that a
# mandatory activity block (lunch, dinner, shopping) always wins contention
# in the score-driven greedy whenever it's feasible. Current max realistic
# attraction prize is 100.
MANDATORY_ACTIVITY_PRIZE = 100_000.0

# Default hour-of-day window for SOLVER_CHOICE placement, so a mandatory
# block's forcing prize doesn't just get grabbed at park open because that's
# the first opportunity -- without this, "Dinner" could get scheduled at
# 8am, which defeats the point of naming it dinner. (hour, minute) pairs.
_SOLVER_CHOICE_DEFAULT_WINDOW: dict[ActivityKind, tuple[tuple[int, int], tuple[int, int]]] = {
    ActivityKind.LUNCH: ((11, 0), (14, 0)),
    ActivityKind.DINNER: ((17, 0), (20, 30)),
}


def _location_and_slug(entry_id: str, child_by_id: dict[str, ChildEntity]) -> tuple[Coordinates | None, str | None]:
    child = child_by_id.get(entry_id)
    slug = child.slug if child else None
    location = (
        Coordinates(latitude=child.location.latitude, longitude=child.location.longitude)
        if child and child.location
        else None
    )
    return location, slug


def _build_node(
    entry: LiveDataEntry,
    child_by_id: dict[str, ChildEntity],
    ride_duration_map: RideDurationMap,
    show_category_map: ShowCategoryMap,
    reliability_profile: ReliabilityProfile,
    land_map: LandMap,
    base_prize: float,
    mandatory: bool = False,
) -> Node | None:
    """Shared per-entry Node construction, used by both build_candidate_nodes()
    (tier-filtered, fed to a solver) and build_listing_nodes() (unfiltered,
    for display) -- the extraction logic is identical, only the inclusion
    filter and base_prize differ between the two callers."""
    location, slug = _location_and_slug(entry.id, child_by_id)
    time_windows = _time_windows_for(entry)
    if not time_windows:
        return None  # no schedulable window (e.g. a show with no announced showtimes)

    lightning_lane_type, lightning_lane_window, lightning_lane_price = _lightning_lane_info(entry)
    return Node(
        id=entry.id,
        name=entry.name,
        kind=entry.entityType,
        base_prize=base_prize,
        service_time_minutes=_service_time_minutes(entry, ride_duration_map, slug),
        wait_estimate_minutes=_wait_minutes(entry),
        wait_forecast=_wait_forecast_for(entry),
        time_windows=time_windows,
        lightning_lane_type=lightning_lane_type,
        lightning_lane_window=lightning_lane_window,
        lightning_lane_price=lightning_lane_price,
        is_water_ride=reliability_profile.is_water_ride(slug, entry.id),
        reliability_tier=reliability_profile.tier_for(slug, entry.id),
        location=location,
        land=land_map.land_for(slug, entry.id),
        show_category=show_category_map.category_for(slug, entry.id) if entry.entityType == "SHOW" else None,
        mandatory=mandatory,
    )


def build_candidate_nodes(
    children: ChildrenResponse,
    live: LiveResponse,
    preferences: Preferences,
    reliability_profile: ReliabilityProfile,
    objective: Objective,
    land_map: LandMap | None = None,
    ride_duration_map: RideDurationMap | None = None,
    show_category_map: ShowCategoryMap | None = None,
) -> list[Node]:
    land_map = land_map or LandMap()
    ride_duration_map = ride_duration_map or RideDurationMap()
    show_category_map = show_category_map or ShowCategoryMap()
    child_by_id: dict[str, ChildEntity] = {child.id: child for child in children.children}
    nodes: list[Node] = []

    for entry in live.liveData:
        if entry.entityType not in ("ATTRACTION", "SHOW"):
            continue
        if entry.status != "OPERATING":
            continue

        _, slug = _location_and_slug(entry.id, child_by_id)

        # The specific parade/nighttime show the guest picked (onboarding) is
        # mandatory the same way a meal block is -- guaranteed a scheduling
        # attempt, honestly reported if it truly can't fit, and (for
        # ALL_RIDES_CHALLENGE below) included despite that mode otherwise
        # excluding SHOW entities entirely. Matched by exact id, not category --
        # a day can run several shows in the same category (e.g. multiple
        # nighttime spectaculars), and the guest asked for one specific show,
        # not "any show like this."
        wants_this_show = entry.id in (preferences.desired_parade_id, preferences.desired_nighttime_show_id)

        base_prize = preferences.base_prize_for(slug, entry.id)
        if objective == "MAXIMIZE_PRIZE":
            if base_prize is None and not wants_this_show:
                continue  # guest tagged this attraction/show SKIP
        else:  # ALL_RIDES_CHALLENGE: tiers ignored for inclusion, kept only as a tie-break
            if entry.entityType == "SHOW" and not wants_this_show:
                continue  # shows stay excluded here unless explicitly requested
            base_prize = base_prize if base_prize is not None else DEFAULT_BASE_PRIZE

        node = _build_node(
            entry,
            child_by_id,
            ride_duration_map,
            show_category_map,
            reliability_profile,
            land_map,
            base_prize=MANDATORY_ACTIVITY_PRIZE if wants_this_show else base_prize,
            mandatory=wants_this_show,
        )
        if node is None:
            continue
        if not preferences.use_lightning_lane:
            node = node.model_copy(
                update={"lightning_lane_type": "NONE", "lightning_lane_window": None, "lightning_lane_price": None}
            )
        original, extra_visits = _repeated_copies(node, preferences, slug)
        nodes.append(original)
        nodes.extend(extra_visits)
    return nodes


def _split_window(windows: list[TimeWindow], count: int, index: int) -> list[TimeWindow]:
    """Splits the first (usually only) operating window into `count` equal
    chronological slices and returns the one at `index`."""
    window = windows[0]
    slice_length = (window.end - window.start) / count
    return [TimeWindow(start=window.start + slice_length * index, end=window.start + slice_length * (index + 1))]


def _repeated_copies(node: Node, preferences: Preferences, slug: str | None) -> tuple[Node, list[Node]]:
    """Splits a guest-requested repeat visit (e.g. repeat_counts={"spacemountain":
    3}) into `count` independent candidates, each restricted to its own slice of
    the attraction's operating window. Without this, duplicate candidates sit at
    the same location with the same wide time window, so a travel-minimizing
    solver treats riding it again immediately as free and clusters them
    back-to-back -- slicing the day up front is what actually spreads them out,
    not a solver-level "no adjacent visits" constraint. Returns (the original
    node, resliced to its own first slice; the N-1 extra suffixed-id copies)."""
    count = preferences.repeat_counts[slug] if slug and slug in preferences.repeat_counts else (
        preferences.repeat_counts.get(node.id, 1)
    )
    if count <= 1:
        return node, []
    original_windows = node.time_windows
    original = node.model_copy(update={"time_windows": _split_window(original_windows, count, 0)})
    extras = [
        node.model_copy(
            update={"id": f"{node.id}-visit-{i}", "time_windows": _split_window(original_windows, count, i - 1)}
        )
        for i in range(2, count + 1)
    ]
    return original, extras


def build_listing_nodes(
    children: ChildrenResponse,
    live: LiveResponse,
    reliability_profile: ReliabilityProfile,
    land_map: LandMap | None = None,
    ride_duration_map: RideDurationMap | None = None,
    show_category_map: ShowCategoryMap | None = None,
) -> list[Node]:
    """Every currently OPERATING attraction/show, regardless of any guest
    tier -- for display only (the onboarding picker, the "didn't make the
    cut" swap listing, "build your own"), never fed to a solver. Guests need
    to see everything to set preferences on it, not a pre-filtered set."""
    land_map = land_map or LandMap()
    ride_duration_map = ride_duration_map or RideDurationMap()
    show_category_map = show_category_map or ShowCategoryMap()
    child_by_id: dict[str, ChildEntity] = {child.id: child for child in children.children}
    nodes: list[Node] = []

    for entry in live.liveData:
        if entry.entityType not in ("ATTRACTION", "SHOW"):
            continue
        if entry.status != "OPERATING":
            continue
        node = _build_node(
            entry, child_by_id, ride_duration_map, show_category_map, reliability_profile, land_map,
            base_prize=DEFAULT_BASE_PRIZE,
        )
        if node is not None:
            nodes.append(node)
    return nodes


def _solver_choice_window(kind: ActivityKind, day_start: datetime, day_end: datetime) -> TimeWindow:
    default = _SOLVER_CHOICE_DEFAULT_WINDOW.get(kind)
    if default is None:
        return TimeWindow(start=day_start, end=day_end)

    (start_h, start_m), (end_h, end_m) = default
    window_start = max(day_start, day_start.replace(hour=start_h, minute=start_m, second=0, microsecond=0))
    window_end = min(day_end, day_start.replace(hour=end_h, minute=end_m, second=0, microsecond=0))
    if window_start >= window_end:
        # The default hour range doesn't fit inside today's actual budget (e.g. a
        # guest leaving before dinner) -- fall back to the whole day rather than
        # producing an unsatisfiable window for a mandatory block.
        return TimeWindow(start=day_start, end=day_end)
    return TimeWindow(start=window_start, end=window_end)


def resolve_park_close(
    schedule: ScheduleResponse, start_time: datetime, planned_departure: datetime | None
) -> datetime:
    """The official closing time, tightened by a guest-specified departure if
    they want to leave earlier -- never extended past the park's real close."""
    official_close = _closing_time_for(schedule, start_time) or (start_time + timedelta(hours=12))
    if planned_departure is not None and planned_departure < official_close:
        return planned_departure
    return official_close


def build_activity_nodes(
    activity_blocks: list[ActivityBlock], day_start: datetime, day_end: datetime
) -> list[Node]:
    """Meal/shopping blocks reuse the exact Node/Solver machinery attractions and
    shows already use -- a narrow feasibility window plus a forcing prize
    constant, not a parallel scheduling subsystem. See PLAN_2 notes."""
    nodes: list[Node] = []
    for i, block in enumerate(activity_blocks):
        if block.placement == BlockPlacement.FIXED_TIME:
            if block.fixed_time is None:
                raise ValueError(f"Activity block '{block.name}' is FIXED_TIME but has no fixed_time.")
            window = TimeWindow(
                start=block.fixed_time, end=block.fixed_time + timedelta(minutes=block.duration_minutes)
            )
        elif block.placement == BlockPlacement.PREFERRED_RANGE:
            if block.range_start is None or block.range_end is None:
                raise ValueError(
                    f"Activity block '{block.name}' is PREFERRED_RANGE but missing range_start/range_end."
                )
            window = TimeWindow(start=block.range_start, end=block.range_end)
        else:  # SOLVER_CHOICE
            window = _solver_choice_window(block.kind, day_start, day_end)

        nodes.append(
            Node(
                id=f"activity-{i}-{block.name}",
                name=block.name,
                kind="ACTIVITY",
                base_prize=MANDATORY_ACTIVITY_PRIZE if block.mandatory else DEFAULT_BASE_PRIZE,
                service_time_minutes=block.duration_minutes,
                wait_estimate_minutes=0.0,
                time_windows=[window],
                mandatory=block.mandatory,
            )
        )
    return nodes


def build_plan_request(
    objective: Objective,
    start_time: datetime,
    park_close: datetime,
    candidate_nodes: list[Node],
    hourly_forecast: list[HourlyWeather],
    preferences: Preferences,
    max_budget_minutes: float | None = None,
) -> PlanRequest:
    budget_minutes = (park_close - start_time).total_seconds() / 60.0
    if max_budget_minutes is not None:
        budget_minutes = min(budget_minutes, max_budget_minutes)

    return PlanRequest(
        objective=objective,
        start_time=start_time,
        park_close=park_close,
        time_budget_minutes=max(budget_minutes, 0.0),
        candidate_nodes=candidate_nodes,
        water_ride_comfort=preferences.water_ride_comfort,
        hourly_forecast=hourly_forecast,
        # getattr(x, "value", x), not str(x) or x.value alone: preferences.model_copy
        # (used by the CLI's --navigation override) sets a raw str, not a
        # re-validated Enum member, so .value would crash on that path -- and
        # str(SomeStrEnum.MEMBER) is the classic gotcha that returns
        # "ClassName.MEMBER", not the plain value, even though it's a str subclass.
        navigation_strategy=getattr(preferences.navigation_strategy, "value", preferences.navigation_strategy),
        land_order=preferences.land_order,
        walking_pace_mph=WALKING_PACE_MPH[
            getattr(preferences.walking_pace, "value", preferences.walking_pace)
        ],
    )


def _time_windows_for(entry: LiveDataEntry) -> list[TimeWindow]:
    if entry.entityType == "SHOW":
        return [TimeWindow(start=s.startTime, end=s.endTime) for s in entry.showtimes]
    return [TimeWindow(start=p.startTime, end=p.endTime) for p in entry.operatingHours]


def _service_time_minutes(entry: LiveDataEntry, ride_duration_map: RideDurationMap, slug: str | None) -> float:
    if entry.entityType == "SHOW" and entry.showtimes:
        first = entry.showtimes[0]
        duration = (first.endTime - first.startTime).total_seconds() / 60.0
        return max(duration, 1.0)
    return ride_duration_map.duration_for(slug, entry.id)


def _wait_minutes(entry: LiveDataEntry) -> float:
    if entry.queue and entry.queue.STANDBY and entry.queue.STANDBY.waitTime is not None:
        return float(entry.queue.STANDBY.waitTime)
    return 0.0


def _wait_forecast_for(entry: LiveDataEntry) -> list[WaitForecastEntry]:
    return [
        WaitForecastEntry(hour=f.time, wait_minutes=float(f.waitTime))
        for f in entry.forecast
        if f.waitTime is not None
    ]


def _lightning_lane_info(
    entry: LiveDataEntry,
) -> tuple[LightningLaneType, TimeWindow | None, PriceInfo | None]:
    queue = entry.queue
    if queue is None:
        return "NONE", None, None

    multi = queue.RETURN_TIME
    if multi and multi.state == "AVAILABLE" and multi.returnStart and multi.returnEnd:
        return "MULTI", TimeWindow(start=multi.returnStart, end=multi.returnEnd), None

    single = queue.PAID_RETURN_TIME
    if single and single.state == "AVAILABLE" and single.returnStart and single.returnEnd:
        return "SINGLE", TimeWindow(start=single.returnStart, end=single.returnEnd), single.price

    return "NONE", None, None


def _closing_time_for(schedule: ScheduleResponse, moment: datetime) -> datetime | None:
    target_date = moment.date().isoformat()
    for entry in schedule.schedule:
        if entry.date == target_date and entry.closingTime is not None:
            return entry.closingTime
    return None


def opening_time_for(schedule: ScheduleResponse, day: datetime) -> datetime | None:
    target_date = day.date().isoformat()
    for entry in schedule.schedule:
        if entry.date == target_date and entry.openingTime is not None:
            return entry.openingTime
    return None
