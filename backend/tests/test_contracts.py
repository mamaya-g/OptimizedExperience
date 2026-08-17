from datetime import datetime

from optimized_experience.optimizer.contracts import Coordinates, TimeWindow, WaitForecastEntry
from conftest import make_attraction


def test_time_window_contains():
    window = TimeWindow(start=datetime(2026, 8, 16, 9, 0), end=datetime(2026, 8, 16, 10, 0))
    assert window.contains(datetime(2026, 8, 16, 9, 30))
    assert not window.contains(datetime(2026, 8, 16, 10, 1))


def test_time_window_overlaps():
    a = TimeWindow(start=datetime(2026, 8, 16, 9, 0), end=datetime(2026, 8, 16, 10, 0))
    b = TimeWindow(start=datetime(2026, 8, 16, 9, 30), end=datetime(2026, 8, 16, 11, 0))
    c = TimeWindow(start=datetime(2026, 8, 16, 10, 0), end=datetime(2026, 8, 16, 11, 0))
    assert a.overlaps(b)
    assert not a.overlaps(c)  # touching, not overlapping (half-open by design)


def test_node_is_feasible_at():
    node = make_attraction(
        "A",
        time_windows=[TimeWindow(start=datetime(2026, 8, 16, 9, 0), end=datetime(2026, 8, 16, 12, 0))],
    )
    assert node.is_feasible_at(datetime(2026, 8, 16, 10, 0))
    assert not node.is_feasible_at(datetime(2026, 8, 16, 13, 0))


def test_node_wait_minutes_at_uses_forecast_for_matching_hour():
    node = make_attraction(
        "A",
        wait_estimate_minutes=30.0,
        wait_forecast=[
            WaitForecastEntry(hour=datetime(2026, 8, 16, 9, 0), wait_minutes=45.0),
            WaitForecastEntry(hour=datetime(2026, 8, 16, 20, 0), wait_minutes=5.0),
        ],
    )
    assert node.wait_minutes_at(datetime(2026, 8, 16, 9, 15)) == 45.0
    assert node.wait_minutes_at(datetime(2026, 8, 16, 20, 45)) == 5.0


def test_node_wait_minutes_at_falls_back_to_static_estimate():
    node = make_attraction("A", wait_estimate_minutes=30.0, wait_forecast=[])
    assert node.wait_minutes_at(datetime(2026, 8, 16, 14, 0)) == 30.0


def test_coordinates_distance_miles_is_symmetric_and_zero_for_same_point():
    a = Coordinates(latitude=33.8121, longitude=-117.9190)
    b = Coordinates(latitude=33.8003, longitude=-117.8827)
    assert a.distance_miles(a) == 0.0
    assert round(a.distance_miles(b), 4) == round(b.distance_miles(a), 4)
    assert 2.0 < a.distance_miles(b) < 2.5
