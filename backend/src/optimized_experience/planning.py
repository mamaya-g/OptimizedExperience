"""Bridges the data layer (live park data, weather, preferences, reliability)
into a PlanRequest the optimizer contract consumes. Kept separate from cli.py
so this orchestration logic is testable without going through argument
parsing.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from optimized_experience.data.models import ChildrenResponse, LiveDataEntry, LiveResponse, ScheduleResponse
from optimized_experience.data.preferences import DEFAULT_BASE_PRIZE, Preferences
from optimized_experience.data.reliability import ReliabilityProfile
from optimized_experience.data.weather_client import HourlyWeather
from optimized_experience.optimizer.contracts import LightningLaneType, Node, Objective, PlanRequest, TimeWindow

# themeparks.wiki does not expose ride/show duration -- this is a documented
# simplification, not a measured value. See plan notes on data limitations.
DEFAULT_ATTRACTION_SERVICE_MINUTES = 4.0


def build_candidate_nodes(
    children: ChildrenResponse,
    live: LiveResponse,
    preferences: Preferences,
    reliability_profile: ReliabilityProfile,
    objective: Objective,
) -> list[Node]:
    slug_by_id = {child.id: child.slug for child in children.children}
    nodes: list[Node] = []

    for entry in live.liveData:
        if entry.entityType not in ("ATTRACTION", "SHOW"):
            continue
        if entry.status != "OPERATING":
            continue

        slug = slug_by_id.get(entry.id)
        time_windows = _time_windows_for(entry)
        if not time_windows:
            continue  # no schedulable window (e.g. a show with no announced showtimes)

        base_prize = preferences.base_prize_for(slug, entry.id)
        if objective == "MAXIMIZE_PRIZE":
            if base_prize is None:
                continue  # guest tagged this attraction/show SKIP
        else:  # ALL_RIDES_CHALLENGE: tiers ignored for inclusion, kept only as a tie-break
            if entry.entityType != "ATTRACTION":
                continue
            base_prize = base_prize if base_prize is not None else DEFAULT_BASE_PRIZE

        lightning_lane_type, lightning_lane_window = _lightning_lane_info(entry)
        nodes.append(
            Node(
                id=entry.id,
                name=entry.name,
                kind=entry.entityType,
                base_prize=base_prize,
                service_time_minutes=_service_time_minutes(entry),
                wait_estimate_minutes=_wait_minutes(entry),
                time_windows=time_windows,
                lightning_lane_type=lightning_lane_type,
                lightning_lane_window=lightning_lane_window,
                is_water_ride=reliability_profile.is_water_ride(slug, entry.id),
                reliability_tier=reliability_profile.tier_for(slug, entry.id),
            )
        )
    return nodes


def build_plan_request(
    objective: Objective,
    start_time: datetime,
    schedule: ScheduleResponse,
    candidate_nodes: list[Node],
    hourly_forecast: list[HourlyWeather],
    preferences: Preferences,
    max_budget_minutes: float | None = None,
) -> PlanRequest:
    park_close = _closing_time_for(schedule, start_time) or (start_time + timedelta(hours=12))
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
    )


def _time_windows_for(entry: LiveDataEntry) -> list[TimeWindow]:
    if entry.entityType == "SHOW":
        return [TimeWindow(start=s.startTime, end=s.endTime) for s in entry.showtimes]
    return [TimeWindow(start=p.startTime, end=p.endTime) for p in entry.operatingHours]


def _service_time_minutes(entry: LiveDataEntry) -> float:
    if entry.entityType == "SHOW" and entry.showtimes:
        first = entry.showtimes[0]
        duration = (first.endTime - first.startTime).total_seconds() / 60.0
        return max(duration, 1.0)
    return DEFAULT_ATTRACTION_SERVICE_MINUTES


def _wait_minutes(entry: LiveDataEntry) -> float:
    if entry.queue and entry.queue.STANDBY and entry.queue.STANDBY.waitTime is not None:
        return float(entry.queue.STANDBY.waitTime)
    return 0.0


def _lightning_lane_info(entry: LiveDataEntry) -> tuple[LightningLaneType, TimeWindow | None]:
    queue = entry.queue
    if queue is None:
        return "NONE", None

    multi = queue.RETURN_TIME
    if multi and multi.state == "AVAILABLE" and multi.returnStart and multi.returnEnd:
        return "MULTI", TimeWindow(start=multi.returnStart, end=multi.returnEnd)

    single = queue.PAID_RETURN_TIME
    if single and single.state == "AVAILABLE" and single.returnStart and single.returnEnd:
        return "SINGLE", TimeWindow(start=single.returnStart, end=single.returnEnd)

    return "NONE", None


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
