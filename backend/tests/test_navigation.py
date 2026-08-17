from datetime import datetime

from optimized_experience.optimizer.contracts import Coordinates, PlanRequest, TimeWindow
from optimized_experience.optimizer.geography import WALKING_PACE_MPH, walk_minutes
from optimized_experience.optimizer.greedy import GreedySolver
from optimized_experience.optimizer.greedy_challenge import GreedyChallengeSolver
from optimized_experience.optimizer.navigation import is_eligible_under_land_order, navigation_cost_minutes
from conftest import CLOSE, START, make_attraction

# Real-ish Disneyland-area coordinates, far enough apart to produce a
# meaningful walk time at any of the three pace presets.
NEAR = Coordinates(latitude=33.8121, longitude=-117.9190)
FAR = Coordinates(latitude=33.8003, longitude=-117.8827)  # ~2.2mi away


def _solve_greedy(nodes, **overrides):
    kwargs = dict(
        objective="MAXIMIZE_PRIZE",
        start_time=START,
        park_close=CLOSE,
        time_budget_minutes=(CLOSE - START).total_seconds() / 60,
        candidate_nodes=nodes,
    )
    kwargs.update(overrides)
    return GreedySolver().solve(PlanRequest(**kwargs))


def _solve_challenge(nodes, **overrides):
    kwargs = dict(
        objective="ALL_RIDES_CHALLENGE",
        start_time=START,
        park_close=CLOSE,
        time_budget_minutes=(CLOSE - START).total_seconds() / 60,
        candidate_nodes=nodes,
    )
    kwargs.update(overrides)
    return GreedyChallengeSolver().solve(PlanRequest(**kwargs))


# --- geography.py ---


def test_walk_minutes_zero_when_location_missing():
    assert walk_minutes(None, NEAR, 2.7) == 0.0
    assert walk_minutes(NEAR, None, 2.7) == 0.0


def test_walk_minutes_scales_inversely_with_pace():
    slow = walk_minutes(NEAR, FAR, WALKING_PACE_MPH["SLOW"])
    fast = walk_minutes(NEAR, FAR, WALKING_PACE_MPH["FAST"])
    assert slow > fast > 0


# --- navigation.py ---


def test_is_eligible_under_land_order_matches_restricted_land():
    node = make_attraction("a", land="Tomorrowland")
    assert is_eligible_under_land_order(node, "Tomorrowland")
    assert not is_eligible_under_land_order(node, "Fantasyland")


def test_is_eligible_under_land_order_unmapped_land_always_eligible():
    node = make_attraction("a", land=None)
    assert is_eligible_under_land_order(node, "Fantasyland")


def test_is_eligible_under_land_order_mandatory_always_eligible():
    node = make_attraction("a", land="Tomorrowland", mandatory=True)
    assert is_eligible_under_land_order(node, "Fantasyland")


def test_navigation_cost_clustered_adds_penalty_on_land_switch():
    cost = navigation_cost_minutes("CLUSTERED", "Fantasyland", "Tomorrowland", base_walk_minutes=5.0)
    assert cost > 5.0


def test_navigation_cost_clustered_no_penalty_within_same_land():
    cost = navigation_cost_minutes("CLUSTERED", "Fantasyland", "Fantasyland", base_walk_minutes=5.0)
    assert cost == 5.0


def test_navigation_cost_time_optimal_never_penalizes():
    cost = navigation_cost_minutes("TIME_OPTIMAL", "Fantasyland", "Tomorrowland", base_walk_minutes=5.0)
    assert cost == 5.0


# --- end-to-end solver behavior ---


def test_time_optimal_walk_time_affects_scheduling_order():
    # A nearby lower-prize ride can beat a distant higher-prize one once real
    # walking time is counted, whereas phase-1 behavior (no location data)
    # would always prefer the higher prize with equal cost. There's no "park
    # entrance" coordinate (documented simplification), so the very first
    # pick never has a walk cost -- use a same-spot anchor to establish a
    # current_location before comparing near vs. far.
    anchor = make_attraction(
        "anchor", base_prize=100, service_time_minutes=1, wait_estimate_minutes=1, location=NEAR
    )
    near_ride = make_attraction(
        "near", base_prize=50, service_time_minutes=3, wait_estimate_minutes=5, location=NEAR
    )
    far_ride = make_attraction(
        "far", base_prize=55, service_time_minutes=3, wait_estimate_minutes=5, location=FAR
    )
    plan = _solve_greedy(
        [anchor, near_ride, far_ride],
        navigation_strategy="TIME_OPTIMAL",
        walking_pace_mph=WALKING_PACE_MPH["SLOW"],
    )
    assert plan.steps[0].node_id == "anchor"
    assert plan.steps[1].node_id == "near"


def test_land_order_visits_first_land_before_second():
    fantasyland_ride = make_attraction("fl", base_prize=10, service_time_minutes=2, wait_estimate_minutes=5,
                                        land="Fantasyland")
    tomorrowland_ride = make_attraction("tl", base_prize=100, service_time_minutes=2, wait_estimate_minutes=5,
                                         land="Tomorrowland")
    plan = _solve_greedy(
        [fantasyland_ride, tomorrowland_ride],
        navigation_strategy="LAND_ORDER",
        land_order=["Fantasyland", "Tomorrowland"],
    )
    # Despite Tomorrowland's ride having far higher prize, Fantasyland (first
    # in the order) must be visited first.
    assert plan.steps[0].node_id == "fl"
    assert plan.steps[1].node_id == "tl"


def test_land_order_advances_when_first_land_exhausted():
    fantasyland_ride = make_attraction("fl", base_prize=10, service_time_minutes=2, wait_estimate_minutes=5,
                                        land="Fantasyland")
    tomorrowland_ride = make_attraction("tl", base_prize=10, service_time_minutes=2, wait_estimate_minutes=5,
                                         land="Tomorrowland")
    plan = _solve_greedy(
        [fantasyland_ride, tomorrowland_ride],
        navigation_strategy="LAND_ORDER",
        land_order=["Fantasyland", "Tomorrowland"],
    )
    assert {s.node_id for s in plan.steps} == {"fl", "tl"}
    assert plan.unscheduled_node_ids == []


def test_land_order_works_in_challenge_mode_too():
    fantasyland_ride = make_attraction("fl", base_prize=10, service_time_minutes=2, wait_estimate_minutes=5,
                                        land="Fantasyland")
    tomorrowland_ride = make_attraction("tl", base_prize=10, service_time_minutes=2, wait_estimate_minutes=5,
                                         land="Tomorrowland")
    plan = _solve_challenge(
        [fantasyland_ride, tomorrowland_ride],
        navigation_strategy="LAND_ORDER",
        land_order=["Fantasyland", "Tomorrowland"],
    )
    assert plan.steps[0].node_id == "fl"
    assert plan.steps[1].node_id == "tl"


def test_clustered_prefers_staying_in_land_over_marginally_better_option():
    current_land_ride = make_attraction(
        "same_land", base_prize=50, service_time_minutes=3, wait_estimate_minutes=5, land="Fantasyland"
    )
    cross_land_ride = make_attraction(
        "other_land", base_prize=52, service_time_minutes=3, wait_estimate_minutes=5, land="Tomorrowland"
    )
    anchor = make_attraction(
        "anchor", base_prize=100, service_time_minutes=1, wait_estimate_minutes=1, land="Fantasyland"
    )
    plan = _solve_greedy([anchor, current_land_ride, cross_land_ride], navigation_strategy="CLUSTERED")
    # After visiting the Fantasyland anchor, the same-land option should win
    # over the barely-higher-prize cross-land option once the land-switch
    # penalty applies.
    assert plan.steps[1].node_id == "same_land"
