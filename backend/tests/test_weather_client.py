from pathlib import Path

from optimized_experience.data.weather_client import ReplayWeatherSource

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "disneyland_aug16" / "weather_hourly.json"


def test_replay_weather_source_parses_hourly_periods():
    source = ReplayWeatherSource(FIXTURE_PATH)
    forecast = source.get_hourly_forecast()
    assert forecast
    first = forecast[0]
    assert isinstance(first.temperature_f, float)
    assert first.short_forecast
    assert first.hour is not None
