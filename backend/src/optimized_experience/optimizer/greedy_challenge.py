"""TSPTW-style greedy heuristic for the ALL_RIDES_CHALLENGE objective: every
currently-operating attraction becomes mandatory, and the objective shifts
from maximizing prize to feasibly completing the full set -- so selection is
driven by earliest deadline (soonest-closing time window), not by score.
Reuses the same Lightning Lane capacity-1 resource logic as GreedySolver
(see lightning_lane.py) since that constraint is identical in both modes, and
the same navigation threading (real walk-time, three strategies) via
optimizer/navigation.py and geography.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import NamedTuple

from optimized_experience.optimizer import lightning_lane, navigation
from optimized_experience.optimizer.contracts import (
    Coordinates,
    LightningLaneHold,
    Node,
    Plan,
    PlanRequest,
    PlanStep,
    TimeWindow,
)
from optimized_experience.optimizer.geography import walk_minutes

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
    wait_minutes: float
    service_minutes: float


class _NavState(NamedTuple):
    """See greedy.py's _NavState -- identical role here."""

    current_location: Coordinates | None
    current_land: str | None
    restricted_land: str | None


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
        # "mandatory" here means "this challenge mode requires attempting it" (every
        # attraction, plus any guest-declared mandatory activity block) -- distinct
        # from Node.mandatory, which only activity blocks set. The two overlap for
        # activities and are used below to split unscheduled reporting.
        mandatory = {
            node.id: node
            for node in request.candidate_nodes
            if node.id not in request.already_visited_ids
            and (node.kind == "ATTRACTION" or (node.kind == "ACTIVITY" and node.mandatory))
        }
        current_hold = request.active_lightning_lane_hold
        steps: list[PlanStep] = []
        total_prize = 0.0

        land_order_index = 0
        nav = _NavState(
            current_location=None,
            current_land=None,
            restricted_land=(
                request.land_order[0]
                if request.navigation_strategy == "LAND_ORDER" and request.land_order
                else None
            ),
        )

        while mandatory and clock < budget_end:
            current_hold = lightning_lane.expire_if_needed(current_hold, clock)

            best = self._earliest_deadline_candidate(mandatory, clock, budget_end, current_hold, request, nav)
            if best is None:
                if (
                    request.navigation_strategy == "LAND_ORDER"
                    and land_order_index + 1 < len(request.land_order)
                ):
                    land_order_index += 1
                    nav = nav._replace(restricted_land=request.land_order[land_order_index])
                    continue
                break

            steps.append(
                PlanStep(
                    node_id=best.node.id,
                    node_name=best.node.name,
                    action=best.action,
                    planned_arrival=best.arrival,
                    planned_departure=best.arrival + timedelta(minutes=best.cost_minutes),
                    rationale=best.rationale,
                    wait_minutes=best.wait_minutes,
                    service_minutes=best.service_minutes,
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
                if not best.node.mandatory:
                    # Same rationale as GreedySolver: a mandatory activity block's
                    # forcing prize constant isn't a real value signal.
                    total_prize += best.node.base_prize
                del mandatory[best.node.id]
                if current_hold is not None and current_hold.node_id == best.node.id:
                    current_hold = lightning_lane.mark_redeemed(current_hold)
                nav = nav._replace(current_location=best.node.location, current_land=best.node.land)

        return Plan(
            steps=steps,
            total_prize=total_prize,
            solver_name=SOLVER_NAME,
            unscheduled_node_ids=[nid for nid, n in mandatory.items() if not n.mandatory],
            unscheduled_mandatory_node_ids=[nid for nid, n in mandatory.items() if n.mandatory],
        )

    def _earliest_deadline_candidate(
        self,
        mandatory: dict[str, Node],
        clock: datetime,
        budget_end: datetime,
        current_hold: LightningLaneHold | None,
        request: PlanRequest,
        nav: _NavState,
    ) -> _Candidate | None:
        candidates: list[_Candidate] = []
        for node in mandatory.values():
            if request.navigation_strategy == "LAND_ORDER" and not navigation.is_eligible_under_land_order(
                node, nav.restricted_land
            ):
                continue
            candidates.extend(self._candidates_for_node(node, clock, budget_end, current_hold, request, nav))
        if not candidates:
            return None
        return min(candidates, key=lambda c: (c.deadline, -c.node.base_prize, c.cost_minutes))

    @staticmethod
    def _navigation_cost(node: Node, request: PlanRequest, nav: _NavState) -> float:
        base = walk_minutes(nav.current_location, node.location, request.walking_pace_mph)
        return navigation.navigation_cost_minutes(request.navigation_strategy, nav.current_land, node.land, base)

    def _candidates_for_node(
        self,
        node: Node,
        clock: datetime,
        budget_end: datetime,
        current_hold: LightningLaneHold | None,
        request: PlanRequest,
        nav: _NavState,
    ) -> list[_Candidate]:
        nav_cost = self._navigation_cost(node, request, nav)
        candidates: list[_Candidate] = []
        held_by_this = lightning_lane.is_held_by(current_hold, node)

        if held_by_this:
            assert current_hold is not None
            # Offer the redemption even if its window hasn't opened yet, so the
            # solver can "wait" for its own hold when nothing else is actionable
            # right now instead of giving up.
            arrival = max(clock, current_hold.return_start)
            if arrival <= current_hold.return_end:
                cost = max(
                    _LL_NOMINAL_ENTRY_WAIT_MINUTES + node.service_time_minutes + nav_cost, _MIN_COST_MINUTES
                )
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
                        wait_minutes=_LL_NOMINAL_ENTRY_WAIT_MINUTES,
                        service_minutes=node.service_time_minutes,
                    )
                )
            return candidates  # while holding this node's LL, standby/booking aren't offered

        resource_free = lightning_lane.is_resource_free(current_hold)

        if node.lightning_lane_type == "MULTI" and resource_free and node.lightning_lane_window is not None:
            window = node.lightning_lane_window
            if window.end >= clock and window.start <= budget_end:
                # Booking is an app action -- no travel required, so no nav_cost here.
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
                        wait_minutes=0.0,
                        service_minutes=_LL_BOOKING_OVERHEAD_MINUTES,
                    )
                )

        if node.lightning_lane_type == "SINGLE" and node.lightning_lane_window is not None:
            window = node.lightning_lane_window
            arrival = max(clock, window.start)
            if window.end >= clock:
                cost = max(
                    _LL_NOMINAL_ENTRY_WAIT_MINUTES + node.service_time_minutes + nav_cost, _MIN_COST_MINUTES
                )
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
                            wait_minutes=_LL_NOMINAL_ENTRY_WAIT_MINUTES,
                            service_minutes=node.service_time_minutes,
                        )
                    )

        window = self._earliest_window(node, clock, budget_end)
        if window is not None:
            # max(clock, window.start) matters once ACTIVITY nodes (mandatory
            # meal/shopping blocks) are in the mix -- their window can start
            # later than clock (a preferred range or a fixed time), and without
            # this the solver would report an arrival before the window even
            # opens. No-op for attractions, whose window already covers clock
            # in practice.
            arrival = max(clock, window.start)
            is_activity = node.kind == "ACTIVITY"
            wait = 0.0 if is_activity else node.wait_minutes_at(arrival)
            cost = max(wait + node.service_time_minutes + nav_cost, _MIN_COST_MINUTES)
            if arrival + timedelta(minutes=cost) <= min(window.end, budget_end):
                action = "DO_ACTIVITY" if is_activity else "RIDE_STANDBY"
                rationale = (
                    f"Take time for {node.name} -- it must fit by "
                    f"{window.end.strftime('%-I:%M %p')}."
                    if is_activity
                    else (
                        f"Ride the standby line for {node.name} -- it closes at "
                        f"{window.end.strftime('%-I:%M %p')}, an urgent deadline among remaining rides."
                    )
                )
                candidates.append(
                    _Candidate(
                        node=node,
                        action=action,
                        arrival=arrival,
                        cost_minutes=cost,
                        deadline=window.end,
                        rationale=rationale,
                        wait_minutes=wait,
                        service_minutes=node.service_time_minutes,
                    )
                )
        return candidates

    @staticmethod
    def _earliest_window(node: Node, clock: datetime, budget_end: datetime) -> TimeWindow | None:
        upcoming = [w for w in node.time_windows if w.end >= clock and w.start <= budget_end]
        return min(upcoming, key=lambda w: w.end) if upcoming else None
