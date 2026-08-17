from pathlib import Path

from optimized_experience.data.ride_durations import (
    DEFAULT_DURATION_MINUTES,
    RideDurationMap,
    load_ride_duration_map,
)

EXAMPLE_CONFIG = Path(__file__).parent.parent / "config" / "ride_durations.example.yaml"


def test_load_ride_duration_map_reads_real_config():
    ride_duration_map = load_ride_duration_map(EXAMPLE_CONFIG)
    assert ride_duration_map.duration_for("starwarsriseoftheresistance", "some-entity-id") == 18
    assert ride_duration_map.duration_for("piratesofthecaribbean", "some-entity-id") == 15


def test_duration_for_prefers_slug_over_entity_id():
    ride_duration_map = RideDurationMap(durations={"spacemountain": 3.0, "entity-1": 99.0})
    assert ride_duration_map.duration_for("spacemountain", "entity-1") == 3.0


def test_duration_for_falls_back_to_entity_id_when_slug_unmapped():
    ride_duration_map = RideDurationMap(durations={"entity-1": 7.0})
    assert ride_duration_map.duration_for(None, "entity-1") == 7.0
    assert ride_duration_map.duration_for("unmapped-slug", "entity-1") == 7.0


def test_duration_for_falls_back_to_default_when_wholly_unmapped():
    ride_duration_map = RideDurationMap()
    assert ride_duration_map.duration_for("unmapped-slug", "unmapped-id") == DEFAULT_DURATION_MINUTES
