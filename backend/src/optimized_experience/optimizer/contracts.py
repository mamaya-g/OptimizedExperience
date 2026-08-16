"""Shared optimizer contract: every solver (greedy now, OR-Tools later) consumes
a PlanRequest and returns a Plan through the same Solver.solve() interface, so
swapping solvers is an addition, not a rewrite.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel

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


LightningLaneType = Literal["MULTI", "SINGLE", "NONE"]
NodeKind = Literal["ATTRACTION", "SHOW"]
PlanAction = Literal["RIDE_STANDBY", "BOOK_LIGHTNING_LANE", "REDEEM_LIGHTNING_LANE", "WATCH_SHOW"]
Objective = Literal["MAXIMIZE_PRIZE", "ALL_RIDES_CHALLENGE"]
LightningLaneHoldStatus = Literal["BOOKED", "REDEEMED", "EXPIRED"]


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

    def is_feasible_at(self, moment: datetime) -> bool:
        return any(window.contains(moment) for window in self.time_windows)


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


class PlanStep(BaseModel):
    node_id: str
    node_name: str
    action: PlanAction
    planned_arrival: datetime
    planned_departure: datetime
    rationale: str


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
    disclaimer: str = PLAN_DISCLAIMER


class Solver(Protocol):
    def solve(self, request: PlanRequest) -> Plan: ...
