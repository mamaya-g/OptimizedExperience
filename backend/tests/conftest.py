from __future__ import annotations

from datetime import datetime

import pytest

from optimized_experience.optimizer.contracts import Node, TimeWindow

START = datetime(2026, 8, 16, 9, 0)
CLOSE = datetime(2026, 8, 16, 22, 0)


@pytest.fixture
def park_window() -> TimeWindow:
    return TimeWindow(start=START, end=CLOSE)


def make_attraction(
    id: str,
    name: str = "Attraction",
    base_prize: float = 40.0,
    service_time_minutes: float = 3.0,
    wait_estimate_minutes: float = 10.0,
    time_windows: list[TimeWindow] | None = None,
    lightning_lane_type: str = "NONE",
    lightning_lane_window: TimeWindow | None = None,
    is_water_ride: bool = False,
    reliability_tier: str = "MEDIUM",
) -> Node:
    return Node(
        id=id,
        name=name,
        kind="ATTRACTION",
        base_prize=base_prize,
        service_time_minutes=service_time_minutes,
        wait_estimate_minutes=wait_estimate_minutes,
        time_windows=time_windows or [TimeWindow(start=START, end=CLOSE)],
        lightning_lane_type=lightning_lane_type,
        lightning_lane_window=lightning_lane_window,
        is_water_ride=is_water_ride,
        reliability_tier=reliability_tier,
    )


def make_show(
    id: str,
    name: str = "Show",
    base_prize: float = 60.0,
    service_time_minutes: float = 20.0,
    time_windows: list[TimeWindow] | None = None,
) -> Node:
    return Node(
        id=id,
        name=name,
        kind="SHOW",
        base_prize=base_prize,
        service_time_minutes=service_time_minutes,
        wait_estimate_minutes=0.0,
        time_windows=time_windows or [],
    )
