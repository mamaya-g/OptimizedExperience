"""API-layer tests: exercises the FastAPI endpoints end-to-end against replay
fixtures (no live network), verifying the HTTP contract (request/response
shapes) on top of what test_planning.py already verifies at the unit level.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from optimized_experience.data.client import ReplayDataSource
from optimized_experience.data.weather_client import ReplayWeatherSource

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "disneyland_aug16"
CONFIG_DIR = Path(__file__).parent.parent / "config"

RISE_OF_THE_RESISTANCE_ID = "34b1d70f-11c4-42df-935e-d5582c9f1a8e"
PAINT_THE_NIGHT_ID = "c60e9de0-df2b-4484-9b05-299939dc247a"


class _FixedDatetime(datetime):
    """POST /api/plan always resolves "now" for real (is_replay=False, matching
    production, which never uses replay data) -- but the fixture's live data is
    all dated 2026-08-16, and every attraction's time window falls within that
    one fixed day. Freeze the clock inside it so this test doesn't silently go
    dark the moment the real calendar date moves past the fixture's date."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 8, 16, 9, 0, tzinfo=tz)


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Real gitignored config (config/*.yaml) is a developer-local convenience,
    # not guaranteed to exist -- tests instead assemble a hermetic config dir
    # from the tracked *.example.yaml files, same content shape either way.
    tmp_config = tmp_path / "config"
    tmp_config.mkdir()
    for example in CONFIG_DIR.glob("*.example.yaml"):
        shutil.copy(example, tmp_config / example.name.replace(".example.yaml", ".yaml"))

    import optimized_experience.api.main as api_main
    import optimized_experience.planning as planning_module

    monkeypatch.setattr(api_main, "DEFAULT_CONFIG_DIR", tmp_config)
    monkeypatch.setattr(api_main, "_data_source", ReplayDataSource(FIXTURE_DIR))
    monkeypatch.setattr(api_main, "_weather_source", ReplayWeatherSource(FIXTURE_DIR / "weather_hourly.json"))
    monkeypatch.setattr(planning_module, "datetime", _FixedDatetime)
    return TestClient(api_main.app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_post_plan_returns_a_plan_with_wait_and_service_minutes_on_each_step(client):
    response = client.post("/api/plan", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["plan"]["steps"], "expected at least one scheduled step"
    for step in body["plan"]["steps"]:
        assert "wait_minutes" in step
        assert "service_minutes" in step
    # No greedy/prize jargon leaking into the response shape itself.
    assert body["plan"]["solver_name"] == "ortools_v1"


def test_post_plan_respects_objective_query_param(client):
    response = client.post("/api/plan?objective=all_rides_challenge", json={})
    assert response.status_code == 200


def test_post_plan_accepts_must_go_show_tier(client):
    response = client.post("/api/plan", json={"tiers": {PAINT_THE_NIGHT_ID: "MUST_GO"}})
    assert response.status_code == 200


def test_get_attractions_lists_real_durations_and_lightning_lane_price(client):
    response = client.get("/api/attractions")
    assert response.status_code == 200
    body = response.json()
    by_id = {a["id"]: a for a in body["attractions"]}
    rise = by_id[RISE_OF_THE_RESISTANCE_ID]
    assert rise["duration_minutes"] == 18
    assert rise["lightning_lane_type"] == "SINGLE"
    assert rise["lightning_lane_price"]["formatted"] == "$29.00"


def test_get_attractions_includes_shows(client):
    response = client.get("/api/attractions")
    body = response.json()
    assert any(a["kind"] == "SHOW" for a in body["attractions"])
