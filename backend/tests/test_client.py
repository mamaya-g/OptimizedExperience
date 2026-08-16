from pathlib import Path

from optimized_experience.data.client import ReplayDataSource

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "disneyland_aug16"


def test_replay_data_source_loads_children():
    source = ReplayDataSource(FIXTURE_DIR)
    children = source.get_children()
    assert children.entityType == "PARK"
    assert any(c.entityType == "ATTRACTION" for c in children.children)
    assert any(c.entityType == "SHOW" for c in children.children)


def test_replay_data_source_loads_live_with_queue_data():
    source = ReplayDataSource(FIXTURE_DIR)
    live = source.get_live()
    assert live.liveData
    operating = [e for e in live.liveData if e.status == "OPERATING"]
    assert operating
    with_standby = [e for e in operating if e.queue and e.queue.STANDBY]
    assert with_standby


def test_replay_data_source_loads_schedule():
    source = ReplayDataSource(FIXTURE_DIR)
    schedule = source.get_schedule()
    assert schedule.schedule
    assert schedule.schedule[0].openingTime is not None
    assert schedule.schedule[0].closingTime is not None


def test_live_data_captures_lightning_lane_multi_and_single():
    source = ReplayDataSource(FIXTURE_DIR)
    live = source.get_live()
    has_multi = any(e.queue and e.queue.RETURN_TIME for e in live.liveData)
    has_single = any(e.queue and e.queue.PAID_RETURN_TIME for e in live.liveData)
    assert has_multi
    assert has_single
