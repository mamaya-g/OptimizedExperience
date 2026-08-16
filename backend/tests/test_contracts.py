from datetime import datetime

from optimized_experience.optimizer.contracts import TimeWindow
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
