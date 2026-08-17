from datetime import datetime

from optimized_experience.optimizer.contracts import PlanRequest, TimeWindow
from optimized_experience.optimizer.greedy import GreedySolver
from optimized_experience.optimizer.greedy_challenge import GreedyChallengeSolver
from optimized_experience.optimizer.ortools_solver import ORToolsSolver
from conftest import CLOSE, START, make_activity, make_attraction, make_show


def _solve(nodes, objective="MAXIMIZE_PRIZE", **overrides):
    kwargs = dict(
        objective=objective,
        start_time=START,
        park_close=CLOSE,
        time_budget_minutes=(CLOSE - START).total_seconds() / 60,
        candidate_nodes=nodes,
    )
    kwargs.update(overrides)
    return ORToolsSolver().solve(PlanRequest(**kwargs))


def test_all_nodes_scheduled_when_they_all_fit():
    nodes = [
        make_attraction("a", base_prize=100, service_time_minutes=3, wait_estimate_minutes=20),
        make_attraction("b", base_prize=40, service_time_minutes=2, wait_estimate_minutes=10),
        make_show(
            "c", base_prize=60, service_time_minutes=20,
            time_windows=[TimeWindow(start=datetime(2026, 8, 16, 14, 0), end=datetime(2026, 8, 16, 14, 30))],
        ),
    ]
    plan = _solve(nodes)
    assert plan.unscheduled_node_ids == []
    assert plan.unscheduled_mandatory_node_ids == []
    assert {s.node_id for s in plan.steps} == {"a", "b", "c"}
    assert plan.total_prize == 200.0


def test_attraction_closing_mid_day_is_only_feasible_before_close():
    early_close = TimeWindow(start=START, end=datetime(2026, 8, 16, 10, 0))
    node = make_attraction(
        "early_bird", base_prize=100, service_time_minutes=5,
        wait_estimate_minutes=200, time_windows=[early_close],
    )
    plan = _solve([node])
    assert plan.unscheduled_node_ids == ["early_bird"]
    assert plan.steps == []


def test_lightning_lane_preferred_over_long_standby_wait():
    ll_window = TimeWindow(start=datetime(2026, 8, 16, 9, 30), end=datetime(2026, 8, 16, 10, 30))
    node = make_attraction(
        "matterhorn", base_prize=100, service_time_minutes=3, wait_estimate_minutes=60,
        lightning_lane_type="MULTI", lightning_lane_window=ll_window,
    )
    plan = _solve([node])
    assert len(plan.steps) == 1
    assert plan.steps[0].action == "REDEEM_LIGHTNING_LANE"


def test_falls_back_to_standby_when_lightning_lane_window_is_infeasible_in_context():
    # Regression: an earlier version of the solver picked one option per node
    # (standby vs. LL) upfront by lowest nominal wait, before solving -- so if
    # the LL window's specific timing didn't fit around a competing priority,
    # the whole node got dropped even though standby would have fit fine.
    # Found via scripts/compare_solvers.py showing OR-Tools losing to the
    # greedy: a MUST_GO attraction was silently excluded this way.
    blocker = make_activity(
        "blocker", duration_minutes=60,
        time_windows=[TimeWindow(start=START, end=datetime(2026, 8, 16, 10, 0))],
    )
    ll_window = TimeWindow(start=START, end=datetime(2026, 8, 16, 9, 30))  # closes before the blocker frees up
    target = make_attraction(
        "target", base_prize=100, service_time_minutes=3, wait_estimate_minutes=10,
        lightning_lane_type="MULTI", lightning_lane_window=ll_window,
    )
    plan = _solve([blocker, target])
    scheduled_target_steps = [s for s in plan.steps if s.node_id == "target"]
    assert len(scheduled_target_steps) == 1
    assert scheduled_target_steps[0].action == "RIDE_STANDBY"  # not dropped just because LL didn't fit
    assert "target" not in plan.unscheduled_node_ids


def test_mandatory_activity_scheduled_over_competing_attractions():
    lunch = make_activity(
        "lunch", time_windows=[TimeWindow(start=datetime(2026, 8, 16, 12, 0), end=datetime(2026, 8, 16, 13, 0))],
    )
    rival = make_attraction(
        "rival", base_prize=100, service_time_minutes=3, wait_estimate_minutes=5,
        time_windows=[TimeWindow(start=datetime(2026, 8, 16, 12, 0), end=datetime(2026, 8, 16, 13, 0))],
    )
    plan = _solve([lunch, rival])
    actions = [s.action for s in plan.steps]
    assert "DO_ACTIVITY" in actions
    assert "lunch" not in plan.unscheduled_mandatory_node_ids


def test_infeasible_mandatory_activity_honestly_reported():
    late_dinner = make_activity(
        "dinner", time_windows=[TimeWindow(start=datetime(2026, 8, 16, 23, 0), end=datetime(2026, 8, 16, 23, 45))],
    )
    plan = _solve([late_dinner])
    assert plan.unscheduled_mandatory_node_ids == ["dinner"]
    assert plan.unscheduled_node_ids == []


def test_mandatory_activity_prize_does_not_inflate_total_prize():
    lunch = make_activity(
        "lunch", time_windows=[TimeWindow(start=datetime(2026, 8, 16, 12, 0), end=datetime(2026, 8, 16, 13, 0))],
    )
    attraction = make_attraction("a", base_prize=40, service_time_minutes=3, wait_estimate_minutes=5)
    plan = _solve([lunch, attraction])
    assert plan.total_prize == 40.0


def test_all_rides_challenge_visits_everything_when_feasible():
    nodes = [
        make_attraction(f"r{i}", base_prize=10, service_time_minutes=2, wait_estimate_minutes=5)
        for i in range(5)
    ]
    plan = _solve(nodes, objective="ALL_RIDES_CHALLENGE")
    assert plan.unscheduled_node_ids == []
    assert {s.node_id for s in plan.steps} == {n.id for n in nodes}


def test_all_rides_challenge_honest_unscheduled_when_infeasible():
    short_close = datetime(2026, 8, 16, 11, 0)
    nodes = [
        make_attraction(f"r{i}", base_prize=50, service_time_minutes=3, wait_estimate_minutes=40)
        for i in range(5)
    ]
    plan = _solve(nodes, objective="ALL_RIDES_CHALLENGE", park_close=short_close, time_budget_minutes=120)
    assert plan.unscheduled_node_ids
    assert set(plan.unscheduled_node_ids).issubset({n.id for n in nodes})


def test_empty_candidates_returns_empty_plan():
    plan = _solve([])
    assert plan.steps == []
    assert plan.total_prize == 0.0


# --- the key sanity check: OR-Tools should never do *worse* than the greedy ---


def _scenario_scored_by_both(nodes, objective="MAXIMIZE_PRIZE", **overrides):
    request_kwargs = dict(
        objective=objective,
        start_time=START,
        park_close=CLOSE,
        time_budget_minutes=(CLOSE - START).total_seconds() / 60,
        candidate_nodes=nodes,
    )
    request_kwargs.update(overrides)
    request = PlanRequest(**request_kwargs)
    solver = GreedySolver() if objective == "MAXIMIZE_PRIZE" else GreedyChallengeSolver()
    return solver.solve(request), ORToolsSolver().solve(request)


def test_ortools_matches_or_beats_greedy_simple_scenario():
    nodes = [
        make_attraction("a", base_prize=100, service_time_minutes=3, wait_estimate_minutes=20),
        make_attraction("b", base_prize=40, service_time_minutes=2, wait_estimate_minutes=10),
        make_attraction("c", base_prize=10, service_time_minutes=2, wait_estimate_minutes=60),
    ]
    greedy_plan, ortools_plan = _scenario_scored_by_both(nodes)
    assert ortools_plan.total_prize >= greedy_plan.total_prize


def test_ortools_matches_or_beats_greedy_with_lightning_lane_and_shows():
    ll_window = TimeWindow(start=datetime(2026, 8, 16, 9, 30), end=datetime(2026, 8, 16, 10, 30))
    nodes = [
        make_attraction(
            "matterhorn", base_prize=100, service_time_minutes=3, wait_estimate_minutes=60,
            lightning_lane_type="MULTI", lightning_lane_window=ll_window,
        ),
        make_attraction("b", base_prize=40, service_time_minutes=2, wait_estimate_minutes=10),
        make_show(
            "show", base_prize=60, service_time_minutes=20,
            time_windows=[TimeWindow(start=datetime(2026, 8, 16, 14, 0), end=datetime(2026, 8, 16, 14, 30))],
        ),
    ]
    greedy_plan, ortools_plan = _scenario_scored_by_both(nodes)
    assert ortools_plan.total_prize >= greedy_plan.total_prize


def test_ortools_matches_or_beats_greedy_tight_budget():
    nodes = [
        make_attraction(f"r{i}", base_prize=50, service_time_minutes=3, wait_estimate_minutes=40)
        for i in range(5)
    ]
    greedy_plan, ortools_plan = _scenario_scored_by_both(nodes, time_budget_minutes=120)
    assert ortools_plan.total_prize >= greedy_plan.total_prize


def test_ortools_matches_or_beats_greedy_all_rides_challenge():
    nodes = [
        make_attraction(f"r{i}", base_prize=10, service_time_minutes=3, wait_estimate_minutes=30)
        for i in range(8)
    ]
    greedy_plan, ortools_plan = _scenario_scored_by_both(nodes, objective="ALL_RIDES_CHALLENGE", time_budget_minutes=180)
    assert ortools_plan.total_prize >= greedy_plan.total_prize
