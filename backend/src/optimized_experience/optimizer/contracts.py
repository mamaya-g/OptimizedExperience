"""Shared optimizer contract: every solver (greedy now, OR-Tools later) consumes
a PlanRequest and returns a Plan through the same Solver.solve() interface, so
swapping solvers is an addition, not a rewrite.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel

from optimized_experience.data.models import PriceInfo
from optimized_experience.data.preferences import WaterRideComfort
from optimized_experience.data.reliability import ReliabilityTier
from optimized_experience.data.weather_client import HourlyWeather


class TimeWindow(BaseModel):
    start: datetime
    end: datetime

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment <= self.end

    def overlaps(self, other: TimeWindow) -> bool:
        return self.start < other.end and other.start < self.end


_EARTH_RADIUS_MILES = 3958.8


class Coordinates(BaseModel):
    """Kept local to the optimizer contract (not imported from data.models.Location)
    so the contract stays self-contained, the same way TimeWindow already is."""

    latitude: float
    longitude: float

    def distance_miles(self, other: Coordinates) -> float:
        lat1, lon1, lat2, lon2 = (
            math.radians(v) for v in (self.latitude, self.longitude, other.latitude, other.longitude)
        )
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return _EARTH_RADIUS_MILES * 2 * math.asin(math.sqrt(a))


class WaitForecastEntry(BaseModel):
    hour: datetime
    wait_minutes: float


LightningLaneType = Literal["MULTI", "SINGLE", "NONE"]
NodeKind = Literal["ATTRACTION", "SHOW", "ACTIVITY"]
PlanAction = Literal[
    "RIDE_STANDBY", "BOOK_LIGHTNING_LANE", "REDEEM_LIGHTNING_LANE", "WATCH_SHOW", "DO_ACTIVITY"
]
Objective = Literal["MAXIMIZE_PRIZE", "ALL_RIDES_CHALLENGE"]
LightningLaneHoldStatus = Literal["BOOKED", "REDEEMED", "EXPIRED"]
NavigationStrategy = Literal["TIME_OPTIMAL", "LAND_ORDER", "CLUSTERED"]
ShowCategory = Literal["PARADE", "NIGHTTIME_SPECTACULAR", "OTHER"]


class Node(BaseModel):
    id: str
    name: str
    kind: NodeKind
    base_prize: float
    service_time_minutes: float
    wait_estimate_minutes: float
    time_windows: list[TimeWindow]
    lightning_lane_type: LightningLaneType = "NONE"
    lightning_lane_window: TimeWindow | None = None
    is_water_ride: bool = False
    reliability_tier: ReliabilityTier = ReliabilityTier.MEDIUM
    location: Coordinates | None = None
    land: str | None = None
    mandatory: bool = False
    wait_forecast: list[WaitForecastEntry] = []
    show_category: ShowCategory | None = None  # only set for kind == "SHOW"
    lightning_lane_price: PriceInfo | None = None  # only meaningful for lightning_lane_type == "SINGLE"

    def is_feasible_at(self, moment: datetime) -> bool:
        return any(window.contains(moment) for window in self.time_windows)

    def wait_minutes_at(self, moment: datetime) -> float:
        """Forecasted wait for this specific hour if we have it, else the
        current snapshot -- this is what makes "is this easier at night"
        reasoning reflect real predicted data instead of a flat all-day
        assumption."""
        for entry in self.wait_forecast:
            if entry.hour.date() == moment.date() and entry.hour.hour == moment.hour:
                return entry.wait_minutes
        return self.wait_estimate_minutes


class LightningLaneHold(BaseModel):
    node_id: str
    booked_at: datetime
    return_start: datetime
    return_end: datetime
    status: LightningLaneHoldStatus = "BOOKED"


class PlanRequest(BaseModel):
    objective: Objective = "MAXIMIZE_PRIZE"
    start_time: datetime
    park_close: datetime
    time_budget_minutes: float
    candidate_nodes: list[Node]
    active_lightning_lane_hold: LightningLaneHold | None = None
    already_visited_ids: set[str] = set()
    water_ride_comfort: WaterRideComfort = WaterRideComfort.MIND_IF_COOL
    hourly_forecast: list[HourlyWeather] = []
    navigation_strategy: NavigationStrategy = "TIME_OPTIMAL"
    land_order: list[str] = []
    walking_pace_mph: float = 2.7


class PlanStep(BaseModel):
    node_id: str
    node_name: str
    action: PlanAction
    planned_arrival: datetime
    planned_departure: datetime
    rationale: str
    # Required, not defaulted: every solver already knows these values when it
    # builds a PlanStep (they drove its own cost/feasibility math) -- a UI
    # needs the actual numbers (wait time, ride length), not just prose.
    wait_minutes: float
    service_minutes: float


PLAN_DISCLAIMER = (
    "This plan reflects historical reliability patterns and forecast conditions at the "
    "time it was generated -- it is not a prediction of specific ride breakdowns. If a "
    "ride scheduled for later in the day goes down unexpectedly, that's a real-world "
    "event the plan could not foresee, not a plan error. Re-run the planner any time to "
    "get an updated itinerary."
)


class Plan(BaseModel):
    steps: list[PlanStep]
    total_prize: float
    solver_name: str
    unscheduled_node_ids: list[str] = []
    unscheduled_mandatory_node_ids: list[str] = []
    disclaimer: str = PLAN_DISCLAIMER


class Solver(Protocol):
    def solve(self, request: PlanRequest) -> Plan: ...
