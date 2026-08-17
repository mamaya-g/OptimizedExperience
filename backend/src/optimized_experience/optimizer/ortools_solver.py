"""OR-Tools routing solver: a prize-collecting VRPTW (vehicle routing problem
with time windows) formulation using real travel time between attractions'
actual coordinates, solved as a genuine global search rather than the
greedy's single-pass myopic heuristic. This is the "provably near-optimal"
counterpart to greedy.py -- see scripts/compare_solvers.py.

Modeled as an open path (not a closed tour) via a zero-cost synthetic depot:
node 0 is a dummy start/end with no real location, so the mandatory
"return to depot" leg OR-Tools' routing library expects costs nothing and
doesn't distort the schedule.

Attractions with a Lightning Lane alternative get **two** routing indices
(standby and LL), tied together by a shared disjunction with max_cardinality=1
so the solver picks whichever fits the *actual* schedule -- not whichever has
the lower nominal wait in isolation. An earlier version picked one option per
node upfront (lower wait wins) before solving; that pruned a node entirely
whenever its cheaper-looking option didn't time-fit the rest of the route,
even when its other option would have. Caught this via
scripts/compare_solvers.py showing OR-Tools losing to the greedy on a
tight-budget scenario -- a MUST_GO attraction was silently dropped because
its Lightning Lane window's specific timing didn't fit, when standby would
have (see test_ortools_solver.py's
test_falls_back_to_standby_when_lightning_lane_window_is_infeasible_in_context).

The time dimension's convention is: cumul(index) = arrival time at that node,
*before* its own service. So a node's own window constraint deducts its own
service time from the upper bound (`SetRange(start, end - service)`), and the
transit cost between two nodes charges the *origin's* service+wait, not the
destination's (see time_cb's comment) -- an earlier version had this
backwards, which silently attributed every node's own service duration to
the wrong edge in the chain and produced systematically wrong arrival times.

Documented simplifications vs. the greedy (full fidelity isn't tractable in
a routing/CP formulation without piecewise-linear objective terms):
- effective_prize()/wait are computed once per (node, option) at that
  option's earliest feasible time, not re-derived dynamically for whichever
  time it actually ends up being visited.
- Lightning Lane's book-then-redeem two-step and capacity-1 resource aren't
  modeled; redeeming is a single visit, not a separate booking action.
- A node with multiple disjoint time windows (e.g. a mid-day break) only
  considers its first chronological window.

Handles both MAXIMIZE_PRIZE and ALL_RIDES_CHALLENGE in one class: unlike the
greedy pair (which need genuinely different *selection logic* -- score vs.
deadline), the two objectives only differ here in one input, the per-node
skip penalty, so branching internally avoids duplicating the entire routing
setup across two classes.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import NamedTuple

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from optimized_experience.optimizer.contracts import Node, Plan, PlanRequest, PlanStep, TimeWindow
from optimized_experience.optimizer.geography import walk_minutes
from optimized_experience.optimizer.scoring import effective_prize

SOLVER_NAME = "ortools_v1"

_SOLVE_TIME_LIMIT_SECONDS = 5
_MANDATORY_PENALTY = 10_000_000
_CHALLENGE_ATTRACTION_PENALTY = 1_000_000
# Keeps routing "efficiency" a mild tiebreaker in the objective, never
# competitive with prize magnitudes (10-100+ per node) -- see module docstring
# on why time is a pure feasibility constraint here, not something to minimize.
_ARC_COST_DIVISOR = 20
_LL_NOMINAL_ENTRY_WAIT_MINUTES = 5.0  # matches greedy.py's convention


class _VisitOption(NamedTuple):
    node: Node
    window: TimeWindow
    wait_minutes: float
    action: str


_ACTION_BY_KIND = {"ATTRACTION": "RIDE_STANDBY", "SHOW": "WATCH_SHOW", "ACTIVITY": "DO_ACTIVITY"}


class ORToolsSolver:
    def solve(self, request: PlanRequest) -> Plan:
        candidates = [n for n in request.candidate_nodes if n.id not in request.already_visited_ids]
        by_id = {n.id: n for n in candidates}
        if not candidates:
            return Plan(steps=[], total_prize=0.0, solver_name=SOLVER_NAME)

        budget_end = min(
            request.park_close, request.start_time + timedelta(minutes=request.time_budget_minutes)
        )
        budget_minutes = int((budget_end - request.start_time).total_seconds() // 60)
        if budget_minutes <= 0:
            return self._all_unscheduled(candidates)

        options: list[_VisitOption] = []
        option_indices_by_node: dict[str, list[int]] = {}
        infeasible_ids: list[str] = []
        for node in candidates:
            feasible = [
                opt
                for opt in self._build_options(node, request.start_time, budget_end)
                if self._fits_own_window(opt, request.start_time, budget_minutes)
            ]
            if not feasible:
                infeasible_ids.append(node.id)
                continue
            option_indices_by_node[node.id] = [len(options) + i for i in range(len(feasible))]
            options.extend(feasible)

        if not options:
            return self._all_unscheduled(candidates)

        manager = pywrapcp.RoutingIndexManager(len(options) + 1, 1, 0)
        routing = pywrapcp.RoutingModel(manager)

        def time_cb(from_i: int, to_i: int) -> int:
            # cumul(index) = arrival time at index, *before* doing its own
            # service -- so the cost of an edge is "finish what I'm currently
            # doing (from_opt's own service+wait), then travel to the next
            # stop." An earlier version used the *destination's* service time
            # here instead of the origin's, which silently attributed every
            # node's own service time to the wrong edge in the chain -- e.g. a
            # 60-minute mandatory block's duration was never actually charged
            # against the clock, because the edge leaving it only counted
            # whatever came *next*. Caught via a regression test asserting a
            # specific arrival time that came out ~50 minutes too early.
            f, t = manager.IndexToNode(from_i), manager.IndexToNode(to_i)
            if f == 0:
                return 0  # depot has no service; the guest starts fresh at start_time
            from_opt = options[f - 1]
            travel = (
                0.0
                if t == 0
                else walk_minutes(from_opt.node.location, options[t - 1].node.location, request.walking_pace_mph)
            )
            return int(round(travel + from_opt.node.service_time_minutes + from_opt.wait_minutes))

        time_cb_index = routing.RegisterTransitCallback(time_cb)
        routing.AddDimension(time_cb_index, budget_minutes, budget_minutes, True, "Time")
        time_dim = routing.GetDimensionOrDie("Time")

        cost_cb_index = routing.RegisterTransitCallback(lambda i, j: time_cb(i, j) // _ARC_COST_DIVISOR)
        routing.SetArcCostEvaluatorOfAllVehicles(cost_cb_index)

        for i, opt in enumerate(options):
            idx = manager.NodeToIndex(i + 1)
            window_start = max(0, int((opt.window.start - request.start_time).total_seconds() // 60))
            window_end = min(budget_minutes, int((opt.window.end - request.start_time).total_seconds() // 60))
            service = int(round(opt.node.service_time_minutes + opt.wait_minutes))
            time_dim.CumulVar(idx).SetRange(window_start, window_end - service)

        for node_id, positions in option_indices_by_node.items():
            node = by_id[node_id]
            node_options = [options[p] for p in positions]
            routing_indices = [manager.NodeToIndex(p + 1) for p in positions]
            penalty = self._penalty(node, node_options, request)
            routing.AddDisjunction(routing_indices, penalty, 1)

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_parameters.time_limit.FromSeconds(_SOLVE_TIME_LIMIT_SECONDS)

        solution = routing.SolveWithParameters(search_parameters)
        if solution is None:
            return self._all_unscheduled(candidates)

        steps: list[PlanStep] = []
        total_prize = 0.0
        visited_ids: set[str] = set()
        index = routing.Start(0)
        while not routing.IsEnd(index):
            pos = manager.IndexToNode(index)
            if pos != 0:
                opt = options[pos - 1]
                node = opt.node
                visited_ids.add(node.id)
                arrival = request.start_time + timedelta(minutes=solution.Value(time_dim.CumulVar(index)))
                cost = node.service_time_minutes + opt.wait_minutes
                prize = effective_prize(node, opt.window.start, request.hourly_forecast, request.water_ride_comfort)
                if not node.mandatory:
                    total_prize += prize
                steps.append(
                    PlanStep(
                        node_id=node.id,
                        node_name=node.name,
                        action=opt.action,
                        planned_arrival=arrival,
                        planned_departure=arrival + timedelta(minutes=cost),
                        rationale=self._rationale(node, opt, prize),
                        wait_minutes=opt.wait_minutes,
                        service_minutes=node.service_time_minutes,
                    )
                )
            index = solution.Value(routing.NextVar(index))

        unscheduled_ids = infeasible_ids + [nid for nid in option_indices_by_node if nid not in visited_ids]
        return Plan(
            steps=steps,
            total_prize=total_prize,
            solver_name=SOLVER_NAME,
            unscheduled_node_ids=[nid for nid in unscheduled_ids if not by_id[nid].mandatory],
            unscheduled_mandatory_node_ids=[nid for nid in unscheduled_ids if by_id[nid].mandatory],
        )

    @staticmethod
    def _all_unscheduled(candidates: list[Node]) -> Plan:
        return Plan(
            steps=[],
            total_prize=0.0,
            solver_name=SOLVER_NAME,
            unscheduled_node_ids=[n.id for n in candidates if not n.mandatory],
            unscheduled_mandatory_node_ids=[n.id for n in candidates if n.mandatory],
        )

    @staticmethod
    def _fits_own_window(opt: _VisitOption, start_time: datetime, budget_minutes: int) -> bool:
        window_start = max(0, int((opt.window.start - start_time).total_seconds() // 60))
        window_end = min(budget_minutes, int((opt.window.end - start_time).total_seconds() // 60))
        service = int(round(opt.node.service_time_minutes + opt.wait_minutes))
        return window_end - service >= window_start

    @staticmethod
    def _build_options(node: Node, start_time: datetime, budget_end: datetime) -> list[_VisitOption]:
        """Every viable way to visit this node -- standby/show/activity, and
        (for Lightning Lane attractions) redemption during the LL window.
        Both get carried into the model as alternatives so the solver picks
        based on how each actually fits the rest of the schedule, not a
        wait-time comparison made in isolation before solving."""
        options: list[_VisitOption] = []

        reachable = [w for w in node.time_windows if w.end >= start_time and w.start <= budget_end]
        if reachable:
            earliest = min(reachable, key=lambda w: w.start)
            window = TimeWindow(start=max(earliest.start, start_time), end=min(earliest.end, budget_end))
            wait = node.wait_minutes_at(window.start) if node.kind == "ATTRACTION" else 0.0
            options.append(_VisitOption(node, window, wait, _ACTION_BY_KIND[node.kind]))

        if node.kind == "ATTRACTION" and node.lightning_lane_type != "NONE" and node.lightning_lane_window is not None:
            ll = node.lightning_lane_window
            clipped = TimeWindow(start=max(ll.start, start_time), end=min(ll.end, budget_end))
            if clipped.start <= clipped.end:
                options.append(_VisitOption(node, clipped, _LL_NOMINAL_ENTRY_WAIT_MINUTES, "REDEEM_LIGHTNING_LANE"))

        return options

    @staticmethod
    def _penalty(node: Node, node_options: list[_VisitOption], request: PlanRequest) -> int:
        if node.mandatory:
            return _MANDATORY_PENALTY
        if request.objective == "ALL_RIDES_CHALLENGE":
            return _CHALLENGE_ATTRACTION_PENALTY
        # The cost of skipping this node entirely = the best any one of its
        # options could have delivered.
        best_prize = max(
            effective_prize(node, opt.window.start, request.hourly_forecast, request.water_ride_comfort)
            for opt in node_options
        )
        return max(int(round(best_prize)), 1)

    @staticmethod
    def _rationale(node: Node, opt: _VisitOption, prize: float) -> str:
        verb = opt.action.replace("_", " ").title()
        return (
            f"{verb}: {node.name} (base prize {node.base_prize:.0f}) -> effective prize "
            f"{prize:.1f}. Chosen by OR-Tools' global routing search, not a step-by-step heuristic."
        )
