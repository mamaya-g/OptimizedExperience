from datetime import datetime

from optimized_experience.data.preferences import WaterRideComfort
from optimized_experience.data.reliability import ReliabilityTier
from optimized_experience.data.weather_client import HourlyWeather
from optimized_experience.optimizer.scoring import (
    effective_prize,
    reliability_factor,
    weather_comfort_factor,
)
from conftest import make_attraction

MORNING = datetime(2026, 8, 16, 9, 0)
AFTERNOON = datetime(2026, 8, 16, 16, 0)


def test_reliability_factor_boosts_low_tier_in_morning_and_discounts_afternoon():
    assert reliability_factor(ReliabilityTier.LOW, MORNING) > 1.0
    assert reliability_factor(ReliabilityTier.LOW, AFTERNOON) < 1.0


def test_reliability_factor_flat_for_high_and_medium():
    for tier in (ReliabilityTier.HIGH, ReliabilityTier.MEDIUM):
        assert reliability_factor(tier, MORNING) == 1.0
        assert reliability_factor(tier, AFTERNOON) == 1.0


def test_weather_comfort_dont_mind_ignores_conditions():
    cool = HourlyWeather(hour=MORNING, temperature_f=55, short_forecast="Cloudy")
    assert weather_comfort_factor(True, cool, WaterRideComfort.DONT_MIND) == 1.0


def test_weather_comfort_mind_if_cool_discounts_cool_weather():
    cool = HourlyWeather(hour=MORNING, temperature_f=55, short_forecast="Cloudy")
    sunny = HourlyWeather(hour=AFTERNOON, temperature_f=85, short_forecast="Sunny")
    assert weather_comfort_factor(True, cool, WaterRideComfort.MIND_IF_COOL) < 1.0
    assert weather_comfort_factor(True, sunny, WaterRideComfort.MIND_IF_COOL) == 1.0


def test_weather_comfort_only_applies_to_water_rides():
    cool = HourlyWeather(hour=MORNING, temperature_f=55, short_forecast="Cloudy")
    assert weather_comfort_factor(False, cool, WaterRideComfort.MIND_IF_COOL) == 1.0


def test_weather_comfort_prefer_afternoon_boosts_afternoon_hours():
    afternoon_forecast = HourlyWeather(hour=AFTERNOON, temperature_f=85, short_forecast="Sunny")
    morning_forecast = HourlyWeather(hour=MORNING, temperature_f=85, short_forecast="Sunny")
    afternoon_factor = weather_comfort_factor(True, afternoon_forecast, WaterRideComfort.PREFER_AFTERNOON)
    morning_factor = weather_comfort_factor(True, morning_forecast, WaterRideComfort.PREFER_AFTERNOON)
    assert afternoon_factor > morning_factor


def test_effective_prize_combines_both_factors():
    node = make_attraction(
        "A", base_prize=100.0, is_water_ride=True, reliability_tier="LOW"
    )
    cool_afternoon = HourlyWeather(hour=AFTERNOON, temperature_f=55, short_forecast="Cloudy")
    prize = effective_prize(node, AFTERNOON, [cool_afternoon], WaterRideComfort.MIND_IF_COOL)
    # LOW reliability discounts afternoon (x0.7) AND cool weather discounts water ride (x0.5)
    assert prize == 100.0 * 0.7 * 0.5
