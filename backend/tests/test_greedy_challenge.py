from datetime import datetime

from optimized_experience.optimizer.contracts import PlanRequest, TimeWindow
from optimized_experience.optimizer.greedy_challenge import GreedyChallengeSolver
from conftest import CLOSE, START, make_attraction, make_show


def _solve(nodes, **overrides):
    kwargs = dict(
        objective="ALL_RIDES_CHALLENGE",
        start_time=START,
        park_close=CLOSE,
        time_budget_minutes=(CLOSE - START).total_seconds() / 60,
        candidate_nodes=nodes,
    )
    kwargs.update(overrides)
    return GreedyChallengeSolver().solve(PlanRequest(**kwargs))


def test_all_attractions_visited_when_time_allows():
    nodes = [make_attraction(f"r{i}", base_prize=10, service_time_minutes=2,
                              wait_estimate_minutes=5) for i in range(5)]
    plan = _solve(nodes)
    assert plan.unscheduled_node_ids == []
    visited = {s.node_id for s in plan.steps if s.action != "BOOK_LIGHTNING_LANE"}
    assert visited == {n.id for n in nodes}


def test_shows_are_ignored_in_challenge_mode():
    attraction = make_attraction("r1", base_prize=10, service_time_minutes=2, wait_estimate_minutes=5)
    show = make_show(
        "s1", time_windows=[TimeWindow(start=datetime(2026, 8, 16, 14, 0), end=datetime(2026, 8, 16, 14, 30))]
    )
    plan = _solve([attraction, show])
    node_ids = {s.node_id for s in plan.steps}
    assert "s1" not in node_ids
    assert "r1" in node_ids


def test_honest_unscheduled_when_infeasible():
    short_close = datetime(2026, 8, 16, 11, 0)
    nodes = [make_attraction(f"r{i}", base_prize=50, service_time_minutes=3,
                              wait_estimate_minutes=40) for i in range(5)]
    plan = _solve(nodes, park_close=short_close, time_budget_minutes=120)
    assert plan.unscheduled_node_ids
    assert set(plan.unscheduled_node_ids).issubset({n.id for n in nodes})


def test_earliest_deadline_prioritized_over_higher_prize():
    urgent = make_attraction(
        "urgent", base_prize=10, service_time_minutes=2, wait_estimate_minutes=5,
        time_windows=[TimeWindow(start=START, end=datetime(2026, 8, 16, 9, 30))],
    )
    relaxed = make_attraction(
        "relaxed", base_prize=100, service_time_minutes=2, wait_estimate_minutes=5,
        time_windows=[TimeWindow(start=START, end=CLOSE)],
    )
    plan = _solve([urgent, relaxed])
    assert plan.steps[0].node_id == "urgent"  # closes soonest, visited first despite lower prize


def test_lightning_lane_used_in_challenge_mode():
    ll_window = TimeWindow(start=datetime(2026, 8, 16, 9, 30), end=datetime(2026, 8, 16, 10, 30))
    node = make_attraction(
        "matterhorn", base_prize=10, service_time_minutes=3, wait_estimate_minutes=60,
        lightning_lane_type="MULTI", lightning_lane_window=ll_window,
    )
    plan = _solve([node])
    actions = [s.action for s in plan.steps]
    assert "BOOK_LIGHTNING_LANE" in actions
    assert "REDEEM_LIGHTNING_LANE" in actions
