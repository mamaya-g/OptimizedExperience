from __future__ import annotations

from datetime import datetime

import pytest

from optimized_experience.optimizer.contracts import Coordinates, Node, TimeWindow, WaitForecastEntry

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
    location: Coordinates | None = None,
    land: str | None = None,
    mandatory: bool = False,
    wait_forecast: list[WaitForecastEntry] | None = None,
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
        location=location,
        land=land,
        mandatory=mandatory,
        wait_forecast=wait_forecast or [],
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


def make_activity(
    id: str,
    name: str = "Lunch",
    duration_minutes: float = 45.0,
    time_windows: list[TimeWindow] | None = None,
    mandatory: bool = True,
) -> Node:
    return Node(
        id=id,
        name=name,
        kind="ACTIVITY",
        base_prize=100_000.0 if mandatory else 10.0,
        service_time_minutes=duration_minutes,
        wait_estimate_minutes=0.0,
        time_windows=time_windows or [TimeWindow(start=START, end=CLOSE)],
        mandatory=mandatory,
    )
