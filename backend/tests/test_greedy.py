from datetime import datetime

from optimized_experience.data.preferences import WaterRideComfort
from optimized_experience.optimizer.contracts import PlanRequest, TimeWindow
from optimized_experience.optimizer.greedy import GreedySolver
from conftest import CLOSE, START, make_activity, make_attraction, make_show


def _solve(nodes, **overrides):
    kwargs = dict(
        objective="MAXIMIZE_PRIZE",
        start_time=START,
        park_close=CLOSE,
        time_budget_minutes=(CLOSE - START).total_seconds() / 60,
        candidate_nodes=nodes,
    )
    kwargs.update(overrides)
    return GreedySolver().solve(PlanRequest(**kwargs))


def test_prefers_higher_prize_per_minute():
    nodes = [
        make_attraction("cheap", base_prize=40, service_time_minutes=2, wait_estimate_minutes=5),
        make_attraction("pricey", base_prize=100, service_time_minutes=3, wait_estimate_minutes=60),
    ]
    plan = _solve(nodes)
    assert plan.steps[0].node_id == "cheap"  # 40/7 > 100/63


def test_attraction_closing_mid_day_is_only_feasible_before_close():
    early_close = TimeWindow(start=START, end=datetime(2026, 8, 16, 10, 0))
    node = make_attraction("early_bird", base_prize=100, service_time_minutes=5,
                            wait_estimate_minutes=200, time_windows=[early_close])
    # Wait alone would push arrival+cost past the attraction's own closing time.
    plan = _solve([node])
    assert plan.unscheduled_node_ids == ["early_bird"]


def test_two_overlapping_showtimes_only_one_watched():
    window_a = TimeWindow(start=datetime(2026, 8, 16, 14, 0), end=datetime(2026, 8, 16, 14, 30))
    window_b = TimeWindow(start=datetime(2026, 8, 16, 14, 15), end=datetime(2026, 8, 16, 14, 45))
    show_a = make_show("show_a", base_prize=80, service_time_minutes=30, time_windows=[window_a])
    show_b = make_show("show_b", base_prize=90, service_time_minutes=30, time_windows=[window_b])
    plan = _solve([show_a, show_b])
    watched = [s.node_id for s in plan.steps if s.action == "WATCH_SHOW"]
    assert len(watched) == 1


def test_forced_standby_vs_lightning_lane_tradeoff():
    ll_window = TimeWindow(start=datetime(2026, 8, 16, 9, 30), end=datetime(2026, 8, 16, 10, 30))
    node = make_attraction(
        "matterhorn", base_prize=100, service_time_minutes=3, wait_estimate_minutes=60,
        lightning_lane_type="MULTI", lightning_lane_window=ll_window,
    )
    plan = _solve([node])
    actions = [s.action for s in plan.steps]
    assert "BOOK_LIGHTNING_LANE" in actions
    assert "REDEEM_LIGHTNING_LANE" in actions
    assert "RIDE_STANDBY" not in actions  # LL strictly cheaper than the 60-minute standby wait


def test_low_reliability_ride_scored_higher_in_morning_than_afternoon():
    morning_node = make_attraction(
        "low_rel", base_prize=100, service_time_minutes=3, wait_estimate_minutes=10,
        reliability_tier="LOW",
    )
    plan = _solve(
        [morning_node],
        start_time=datetime(2026, 8, 16, 9, 0),
        time_budget_minutes=60,
    )
    assert plan.steps
    assert plan.total_prize == 100 * 1.1  # morning boost applied


def test_water_ride_discounted_when_cool_and_comfort_is_mind_if_cool():
    from optimized_experience.data.weather_client import HourlyWeather

    node = make_attraction("splash", base_prize=100, service_time_minutes=3,
                            wait_estimate_minutes=5, is_water_ride=True)
    cool_forecast = [HourlyWeather(hour=START, temperature_f=55, short_forecast="Cloudy")]
    plan = _solve(
        [node],
        water_ride_comfort=WaterRideComfort.MIND_IF_COOL,
        hourly_forecast=cool_forecast,
    )
    assert plan.total_prize == 50.0  # 100 * 0.5 cool/overcast discount


def test_water_ride_not_discounted_when_comfort_is_dont_mind():
    from optimized_experience.data.weather_client import HourlyWeather

    node = make_attraction("splash", base_prize=100, service_time_minutes=3,
                            wait_estimate_minutes=5, is_water_ride=True)
    cool_forecast = [HourlyWeather(hour=START, temperature_f=55, short_forecast="Cloudy")]
    plan = _solve(
        [node],
        water_ride_comfort=WaterRideComfort.DONT_MIND,
        hourly_forecast=cool_forecast,
    )
    assert plan.total_prize == 100.0


def test_forecasted_wait_overrides_static_estimate_at_scoring_time():
    from optimized_experience.optimizer.contracts import WaitForecastEntry

    # Static estimate says a long wait, but the hourly forecast for the plan's
    # actual start hour says it's short -- the solver should use the forecast.
    node = make_attraction(
        "a", base_prize=100, service_time_minutes=3, wait_estimate_minutes=60,
        wait_forecast=[WaitForecastEntry(hour=START, wait_minutes=5)],
    )
    plan = _solve([node])
    step = plan.steps[0]
    actual_cost_minutes = (step.planned_departure - step.planned_arrival).total_seconds() / 60
    assert actual_cost_minutes == 5 + 3  # forecast (5) + service, not static estimate (60) + service


def test_wait_forecast_falls_back_to_static_estimate_for_unforecasted_hour():
    from optimized_experience.optimizer.contracts import WaitForecastEntry

    node = make_attraction(
        "a", base_prize=100, service_time_minutes=3, wait_estimate_minutes=20,
        wait_forecast=[WaitForecastEntry(hour=datetime(2026, 8, 16, 15, 0), wait_minutes=5)],
    )
    plan = _solve([node])  # solved starting at 9am, no forecast entry for that hour
    step = plan.steps[0]
    actual_cost_minutes = (step.planned_departure - step.planned_arrival).total_seconds() / 60
    assert actual_cost_minutes == 20 + 3  # falls back to the static estimate


def test_mandatory_activity_gets_scheduled_over_competing_attractions():
    lunch = make_activity(
        "lunch", time_windows=[TimeWindow(start=datetime(2026, 8, 16, 12, 0), end=datetime(2026, 8, 16, 13, 30))],
    )
    # A very high-prize attraction competing for the same window -- lunch must still win.
    attraction = make_attraction(
        "rival", base_prize=100, service_time_minutes=3, wait_estimate_minutes=5,
        time_windows=[TimeWindow(start=datetime(2026, 8, 16, 12, 0), end=datetime(2026, 8, 16, 13, 30))],
    )
    plan = _solve([lunch, attraction])
    actions = [s.action for s in plan.steps]
    assert "DO_ACTIVITY" in actions
    assert "lunch" not in plan.unscheduled_mandatory_node_ids


def test_mandatory_activity_prize_does_not_inflate_total_prize():
    # Regression: mandatory activities use a huge forcing prize constant to
    # guarantee scheduling -- that constant must not leak into the
    # guest-facing total_prize metric, or it becomes meaningless (e.g.
    # "200,668" instead of a number that reflects real preferences).
    lunch = make_activity(
        "lunch", time_windows=[TimeWindow(start=datetime(2026, 8, 16, 12, 0), end=datetime(2026, 8, 16, 13, 0))],
    )
    attraction = make_attraction("a", base_prize=40, service_time_minutes=3, wait_estimate_minutes=5)
    plan = _solve([lunch, attraction])
    assert plan.total_prize < 1000  # nowhere near the 100,000 forcing constant
    assert plan.total_prize == 40.0  # only the real attraction's prize counts


def test_infeasible_fixed_time_activity_honestly_reported_as_unscheduled_mandatory():
    # Fixed at a time the budget can't reach: park closes at CLOSE (10pm) but
    # the "reservation" is set for after that.
    late_dinner = make_activity(
        "dinner", time_windows=[TimeWindow(start=datetime(2026, 8, 16, 23, 0), end=datetime(2026, 8, 16, 23, 45))],
    )
    plan = _solve([late_dinner])
    assert plan.unscheduled_mandatory_node_ids == ["dinner"]
    assert plan.unscheduled_node_ids == []
    assert plan.steps == []


def test_unscheduled_nodes_reported_when_time_budget_too_small():
    nodes = [make_attraction(f"r{i}", base_prize=50, service_time_minutes=3,
                              wait_estimate_minutes=40) for i in range(5)]
    plan = _solve(nodes, time_budget_minutes=60)
    assert plan.unscheduled_node_ids
