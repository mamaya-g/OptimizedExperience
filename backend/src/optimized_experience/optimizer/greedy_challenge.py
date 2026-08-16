"""TSPTW-style greedy heuristic for the ALL_RIDES_CHALLENGE objective: every
currently-operating attraction becomes mandatory, and the objective shifts
from maximizing prize to feasibly completing the full set -- so selection is
driven by earliest deadline (soonest-closing time window), not by score.
Reuses the same Lightning Lane capacity-1 resource logic as GreedySolver
(see lightning_lane.py) since that constraint is identical in both modes.
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
    TimeWindow,
)

SOLVER_NAME = "greedy_challenge_v1"

_MIN_COST_MINUTES = 0.5
_LL_NOMINAL_ENTRY_WAIT_MINUTES = 5.0
_LL_BOOKING_OVERHEAD_MINUTES = 2.0


class _Candidate(NamedTuple):
    node: Node
    action: str
    arrival: datetime
    cost_minutes: float
    deadline: datetime
    rationale: str


class GreedyChallengeSolver:
    """Visit every operating attraction in one day, if it's feasible.

    Ignores preference tiers for *inclusion* (every operating attraction is
    mandatory); base_prize is only used to break ties between equally urgent
    deadlines. Reports unscheduled_node_ids honestly if the day's time budget
    can't fit everything, rather than silently dropping attractions.
    """

    def solve(self, request: PlanRequest) -> Plan:
        clock = request.start_time
        budget_end = min(
            request.park_close, request.start_time + timedelta(minutes=request.time_budget_minutes)
        )
        mandatory = {
            node.id: node
            for node in request.candidate_nodes
            if node.kind == "ATTRACTION" and node.id not in request.already_visited_ids
        }
        current_hold = request.active_lightning_lane_hold
        steps: list[PlanStep] = []
        total_prize = 0.0

        while mandatory and clock < budget_end:
            current_hold = lightning_lane.expire_if_needed(current_hold, clock)

            best = self._earliest_deadline_candidate(mandatory, clock, budget_end, current_hold)
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
                assert window is not None
                current_hold = LightningLaneHold(
                    node_id=best.node.id,
                    booked_at=best.arrival,
                    return_start=window.start,
                    return_end=window.end,
                    status="BOOKED",
                )
            else:
                total_prize += best.node.base_prize
                del mandatory[best.node.id]
                if current_hold is not None and current_hold.node_id == best.node.id:
                    current_hold = lightning_lane.mark_redeemed(current_hold)

        return Plan(
            steps=steps,
            total_prize=total_prize,
            solver_name=SOLVER_NAME,
            unscheduled_node_ids=list(mandatory.keys()),
        )

    def _earliest_deadline_candidate(
        self,
        mandatory: dict[str, Node],
        clock: datetime,
        budget_end: datetime,
        current_hold: LightningLaneHold | None,
    ) -> _Candidate | None:
        candidates: list[_Candidate] = []
        for node in mandatory.values():
            candidates.extend(self._candidates_for_node(node, clock, budget_end, current_hold))
        if not candidates:
            return None
        return min(candidates, key=lambda c: (c.deadline, -c.node.base_prize, c.cost_minutes))

    def _candidates_for_node(
        self,
        node: Node,
        clock: datetime,
        budget_end: datetime,
        current_hold: LightningLaneHold | None,
    ) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        held_by_this = lightning_lane.is_held_by(current_hold, node)

        if held_by_this:
            assert current_hold is not None
            # Offer the redemption even if its window hasn't opened yet, so the
            # solver can "wait" for its own hold when nothing else is actionable
            # right now instead of giving up.
            arrival = max(clock, current_hold.return_start)
            if arrival <= current_hold.return_end:
                cost = max(_LL_NOMINAL_ENTRY_WAIT_MINUTES + node.service_time_minutes, _MIN_COST_MINUTES)
                candidates.append(
                    _Candidate(
                        node=node,
                        action="REDEEM_LIGHTNING_LANE",
                        arrival=arrival,
                        cost_minutes=cost,
                        deadline=current_hold.return_end,
                        rationale=(
                            f"Redeem your Lightning Lane hold for {node.name} before it expires at "
                            f"{current_hold.return_end.strftime('%-I:%M %p')}."
                        ),
                    )
                )
            return candidates  # while holding this node's LL, standby/booking aren't offered

        resource_free = lightning_lane.is_resource_free(current_hold)

        if node.lightning_lane_type == "MULTI" and resource_free and node.lightning_lane_window is not None:
            window = node.lightning_lane_window
            if window.end >= clock and window.start <= budget_end:
                cost = _LL_BOOKING_OVERHEAD_MINUTES
                candidates.append(
                    _Candidate(
                        node=node,
                        action="BOOK_LIGHTNING_LANE",
                        arrival=clock,
                        cost_minutes=cost,
                        deadline=window.end,
                        rationale=(
                            f"Book a Lightning Lane hold for {node.name} -- its return window closes "
                            f"at {window.end.strftime('%-I:%M %p')}."
                        ),
                    )
                )

        if node.lightning_lane_type == "SINGLE" and node.lightning_lane_window is not None:
            window = node.lightning_lane_window
            arrival = max(clock, window.start)
            if window.end >= clock:
                cost = max(_LL_NOMINAL_ENTRY_WAIT_MINUTES + node.service_time_minutes, _MIN_COST_MINUTES)
                if arrival + timedelta(minutes=cost) <= min(window.end, budget_end):
                    candidates.append(
                        _Candidate(
                            node=node,
                            action="REDEEM_LIGHTNING_LANE",
                            arrival=arrival,
                            cost_minutes=cost,
                            deadline=window.end,
                            rationale=(
                                f"Use your Lightning Lane Single Pass for {node.name} before it closes at "
                                f"{window.end.strftime('%-I:%M %p')}."
                            ),
                        )
                    )

        window = self._earliest_window(node, clock, budget_end)
        if window is not None:
            cost = max(node.wait_estimate_minutes + node.service_time_minutes, _MIN_COST_MINUTES)
            if clock + timedelta(minutes=cost) <= min(window.end, budget_end):
                candidates.append(
                    _Candidate(
                        node=node,
                        action="RIDE_STANDBY",
                        arrival=clock,
                        cost_minutes=cost,
                        deadline=window.end,
                        rationale=(
                            f"Ride the standby line for {node.name} -- it closes at "
                            f"{window.end.strftime('%-I:%M %p')}, an urgent deadline among remaining rides."
                        ),
                    )
                )
        return candidates

    @staticmethod
    def _earliest_window(node: Node, clock: datetime, budget_end: datetime) -> TimeWindow | None:
        upcoming = [w for w in node.time_windows if w.end >= clock and w.start <= budget_end]
        return min(upcoming, key=lambda w: w.end) if upcoming else None
