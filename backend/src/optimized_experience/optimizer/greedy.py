"""Naive greedy heuristic for the MAXIMIZE_PRIZE objective -- the phase-1
baseline solver. Gets a full vertical slice working end-to-end before any
solver sophistication (OR-Tools) is attempted. Implements the same Solver
contract an OR-Tools solver will implement later, so swapping is an addition.

At each step: among all feasible (node, action) candidates, pick the one with
the highest effective_prize-per-minute, apply it, advance the clock, repeat.
Lightning Lane Multi Pass is modeled as a capacity-1 resource (one BOOKED
hold at a time) -- this is the genuine "Waze" analogue in the project: the
solver continuously re-evaluates when to book/redeem as it walks forward in
simulated time, the same shape as a live re-plan loop.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import NamedTuple

from optimized_experience.optimizer import lightning_lane
from optimized_experience.optimizer.contracts import (
    LightningLaneHold,
    Node,
    Plan,
    PlanRequest,
    PlanStep,
)
from optimized_experience.optimizer.scoring import (
    effective_prize,
    reliability_factor,
    weather_comfort_factor,
    find_forecast_for_hour,
)

SOLVER_NAME = "greedy_v1"

_MIN_COST_MINUTES = 0.5  # score-denominator floor, avoids div-by-zero on near-instant actions
_LL_NOMINAL_ENTRY_WAIT_MINUTES = 5.0
_LL_BOOKING_OVERHEAD_MINUTES = 2.0


class _Candidate(NamedTuple):
    node: Node
    action: str
    arrival: datetime
    cost_minutes: float
    score: float
    rationale: str


def _score(prize: float, clock: datetime, arrival: datetime, cost_minutes: float) -> float:
    """prize-per-minute, counting idle time until `arrival` against the score.

    Without this, an action whose arrival is hours away (a future showtime, a
    Single Pass return window) would look artificially cheap -- its score
    would reflect only the few minutes of redemption cost, not the hours the
    plan sits idle waiting for it, and the greedy would wrongly prefer it
    over closer, genuinely faster options.
    """
    idle_minutes = max((arrival - clock).total_seconds() / 60.0, 0.0)
    return prize / max(idle_minutes + cost_minutes, _MIN_COST_MINUTES)


class GreedySolver:
    def solve(self, request: PlanRequest) -> Plan:
        clock = request.start_time
        budget_end = min(
            request.park_close, request.start_time + timedelta(minutes=request.time_budget_minutes)
        )
        remaining = {
            node.id: node
            for node in request.candidate_nodes
            if node.id not in request.already_visited_ids
        }
        consumed_ids: set[str] = set()
        current_hold = request.active_lightning_lane_hold
        steps: list[PlanStep] = []
        total_prize = 0.0

        while remaining and clock < budget_end:
            current_hold = lightning_lane.expire_if_needed(current_hold, clock)

            best = self._best_candidate(remaining, clock, budget_end, current_hold, request)
            if best is None:
                break

            steps.append(
                PlanStep(
                    node_id=best.node.id,
                    node_name=best.node.name,
                    action=best.action,
                    planned_arrival=best.arrival,
                    planned_departure=best.arrival + timedelta(minutes=best.cost_minutes),
                    rationale=best.rationale,
                )
            )
            clock = best.arrival + timedelta(minutes=best.cost_minutes)

            if best.action == "BOOK_LIGHTNING_LANE":
                window = best.node.lightning_lane_window
                current_hold = LightningLaneHold(
                    node_id=best.node.id,
                    booked_at=best.arrival,
                    return_start=window.start,
                    return_end=window.end,
                    status="BOOKED",
                )
            else:
                total_prize += effective_prize(
                    best.node, best.arrival, request.hourly_forecast, request.water_ride_comfort
                )
                consumed_ids.add(best.node.id)
                del remaining[best.node.id]
                if current_hold is not None and current_hold.node_id == best.node.id:
                    current_hold = lightning_lane.mark_redeemed(current_hold)

        unscheduled = [node_id for node_id in remaining if node_id not in consumed_ids]
        return Plan(
            steps=steps,
            total_prize=total_prize,
            solver_name=SOLVER_NAME,
            unscheduled_node_ids=unscheduled,
        )

    def _best_candidate(
        self,
        remaining: dict[str, Node],
        clock: datetime,
        budget_end: datetime,
        current_hold: LightningLaneHold | None,
        request: PlanRequest,
    ) -> _Candidate | None:
        candidates: list[_Candidate] = []
        for node in remaining.values():
            candidates.extend(
                self._candidates_for_node(node, clock, budget_end, current_hold, request)
            )
        if not candidates:
            return None
        return max(candidates, key=lambda c: c.score)

    def _candidates_for_node(
        self,
        node: Node,
        clock: datetime,
        budget_end: datetime,
        current_hold: LightningLaneHold | None,
        request: PlanRequest,
    ) -> list[_Candidate]:
        if node.kind == "SHOW":
            return self._show_candidates(node, clock, budget_end, current_hold, request)
        return self._attraction_candidates(node, clock, budget_end, current_hold, request)

    def _show_candidates(
        self,
        node: Node,
        clock: datetime,
        budget_end: datetime,
        current_hold: LightningLaneHold | None,
        request: PlanRequest,
    ) -> list[_Candidate]:
        window = self._next_reachable_window(node, clock, budget_end)
        if window is None:
            return []
        arrival = max(clock, window.start)
        if self._would_skip_pending_hold(current_hold, arrival):
            # Don't let a future show jump the clock past an already-booked,
            # not-yet-redeemed Lightning Lane window -- that would waste it.
            return []
        cost = max(node.service_time_minutes, _MIN_COST_MINUTES)
        if arrival + timedelta(minutes=cost) > min(window.end, budget_end):
            return []
        prize = effective_prize(node, arrival, request.hourly_forecast, request.water_ride_comfort)
        return [
            _Candidate(
                node=node,
                action="WATCH_SHOW",
                arrival=arrival,
                cost_minutes=cost,
                score=_score(prize, clock, arrival, cost),
                rationale=self._rationale(node, "watch", arrival, prize, request),
            )
        ]

    def _attraction_candidates(
        self,
        node: Node,
        clock: datetime,
        budget_end: datetime,
        current_hold: LightningLaneHold | None,
        request: PlanRequest,
    ) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        held_by_this = lightning_lane.is_held_by(current_hold, node)

        if held_by_this:
            assert current_hold is not None
            # Offer the redemption even if its window hasn't opened yet (arrival
            # in the future) -- otherwise, when nothing else is actionable right
            # now, the solver has no way to "wait" for its own booked hold and
            # just gives up instead of fast-forwarding to it.
            arrival = max(clock, current_hold.return_start)
            if arrival <= current_hold.return_end:
                cost = max(_LL_NOMINAL_ENTRY_WAIT_MINUTES + node.service_time_minutes, _MIN_COST_MINUTES)
                prize = effective_prize(node, arrival, request.hourly_forecast, request.water_ride_comfort)
                candidates.append(
                    _Candidate(
                        node=node,
                        action="REDEEM_LIGHTNING_LANE",
                        arrival=arrival,
                        cost_minutes=cost,
                        score=_score(prize, clock, arrival, cost),
                        rationale=self._rationale(
                            node, "redeem your Lightning Lane hold for", arrival, prize, request
                        ),
                    )
                )
            return candidates  # while holding this node's LL, standby/booking aren't offered

        resource_free = lightning_lane.is_resource_free(current_hold)

        if node.lightning_lane_type == "MULTI" and resource_free and node.lightning_lane_window is not None:
            window = node.lightning_lane_window
            if window.end >= clock and window.start <= budget_end:
                cost = _LL_BOOKING_OVERHEAD_MINUTES
                anticipated_prize = effective_prize(
                    node, max(clock, window.start), request.hourly_forecast, request.water_ride_comfort
                )
                candidates.append(
                    _Candidate(
                        node=node,
                        action="BOOK_LIGHTNING_LANE",
                        arrival=clock,
                        cost_minutes=cost,
                        score=anticipated_prize / cost,
                        rationale=self._rationale(
                            node, "book a Lightning Lane hold for", clock, anticipated_prize, request
                        ),
                    )
                )

        if node.lightning_lane_type == "SINGLE" and node.lightning_lane_window is not None:
            window = node.lightning_lane_window
            arrival = max(clock, window.start)
            if window.end >= clock and not self._would_skip_pending_hold(current_hold, arrival):
                cost = max(_LL_NOMINAL_ENTRY_WAIT_MINUTES + node.service_time_minutes, _MIN_COST_MINUTES)
                if arrival + timedelta(minutes=cost) <= min(window.end, budget_end):
                    prize = effective_prize(node, arrival, request.hourly_forecast, request.water_ride_comfort)
                    candidates.append(
                        _Candidate(
                            node=node,
                            action="REDEEM_LIGHTNING_LANE",
                            arrival=arrival,
                            cost_minutes=cost,
                            score=_score(prize, clock, arrival, cost),
                            rationale=self._rationale(
                                node, "use your Lightning Lane Single Pass for", arrival, prize, request
                            ),
                        )
                    )

        if node.is_feasible_at(clock):
            cost = max(node.wait_estimate_minutes + node.service_time_minutes, _MIN_COST_MINUTES)
            active_window = next(w for w in node.time_windows if w.contains(clock))
            if clock + timedelta(minutes=cost) <= min(active_window.end, budget_end):
                prize = effective_prize(node, clock, request.hourly_forecast, request.water_ride_comfort)
                candidates.append(
                    _Candidate(
                        node=node,
                        action="RIDE_STANDBY",
                        arrival=clock,
                        cost_minutes=cost,
                        score=prize / cost,
                        rationale=self._rationale(node, "ride the standby line for", clock, prize, request),
                    )
                )
        return candidates

    @staticmethod
    def _would_skip_pending_hold(current_hold: LightningLaneHold | None, arrival: datetime) -> bool:
        return (
            current_hold is not None
            and current_hold.status == "BOOKED"
            and current_hold.return_end < arrival
        )

    @staticmethod
    def _next_reachable_window(node: Node, clock: datetime, budget_end: datetime):
        upcoming = [w for w in node.time_windows if w.end >= clock and w.start <= budget_end]
        return min(upcoming, key=lambda w: w.start) if upcoming else None

    @staticmethod
    def _rationale(node: Node, verb: str, moment: datetime, prize: float, request: PlanRequest) -> str:
        reliability = reliability_factor(node.reliability_tier, moment)
        weather = weather_comfort_factor(
            node.is_water_ride,
            find_forecast_for_hour(request.hourly_forecast, moment),
            request.water_ride_comfort,
        )
        parts = [f"{verb.capitalize()} {node.name} (base prize {node.base_prize:.0f}"]
        if reliability != 1.0:
            parts.append(f", reliability adjustment x{reliability:.2f}")
        if weather != 1.0:
            parts.append(f", weather adjustment x{weather:.2f}")
        parts.append(f") -> effective prize {prize:.1f} at {moment.strftime('%-I:%M %p')}.")
        return "".join(parts)
