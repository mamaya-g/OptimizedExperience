"""effective_prize(): the single mechanism behind both breakdown-risk and
weather-comfort adjustments -- an hour-dependent multiplier on a node's base
prize, approximating an Orienteering Problem with Stochastic Profits (OPSP)
via expected-value discounting instead of a full stochastic solver.
"""

from __future__ import annotations

from datetime import datetime

from optimized_experience.data.preferences import WaterRideComfort
from optimized_experience.data.reliability import ReliabilityTier
from optimized_experience.data.weather_client import HourlyWeather
from optimized_experience.optimizer.contracts import Node

# LOW-reliability rides: a morning breakdown still leaves the rest of the day
# to retry, so mildly boost them early; a late breakdown forecloses the ride
# entirely, so discount them once retry time runs out.
_LOW_RELIABILITY_MORNING_BOOST = 1.1
_LOW_RELIABILITY_AFTERNOON_DISCOUNT = 0.7
_LOW_RELIABILITY_CUTOVER_HOUR = 14  # 2pm local

_COOL_TEMPERATURE_THRESHOLD_F = 72.0
_OVERCAST_KEYWORDS = ("cloud", "rain", "shower", "storm", "overcast")


def reliability_factor(tier: ReliabilityTier, moment: datetime) -> float:
    if tier is not ReliabilityTier.LOW:
        return 1.0
    if moment.hour < _LOW_RELIABILITY_CUTOVER_HOUR:
        return _LOW_RELIABILITY_MORNING_BOOST
    return _LOW_RELIABILITY_AFTERNOON_DISCOUNT


def weather_comfort_factor(
    is_water_ride: bool,
    forecast: HourlyWeather | None,
    comfort: WaterRideComfort,
) -> float:
    if not is_water_ride or comfort is WaterRideComfort.DONT_MIND or forecast is None:
        return 1.0

    if comfort is WaterRideComfort.PREFER_AFTERNOON:
        return 1.3 if forecast.hour.hour >= 13 else 0.8

    # MIND_IF_COOL: discount when it's cool or the sky suggests it's not sunny.
    is_cool_or_overcast = forecast.temperature_f < _COOL_TEMPERATURE_THRESHOLD_F or any(
        keyword in forecast.short_forecast.lower() for keyword in _OVERCAST_KEYWORDS
    )
    return 0.5 if is_cool_or_overcast else 1.0


def find_forecast_for_hour(forecast: list[HourlyWeather], moment: datetime) -> HourlyWeather | None:
    for entry in forecast:
        if entry.hour.date() == moment.date() and entry.hour.hour == moment.hour:
            return entry
    return None


def effective_prize(
    node: Node,
    moment: datetime,
    hourly_forecast: list[HourlyWeather],
    water_ride_comfort: WaterRideComfort,
) -> float:
    reliability = reliability_factor(node.reliability_tier, moment)
    weather = weather_comfort_factor(
        node.is_water_ride,
        find_forecast_for_hour(hourly_forecast, moment),
        water_ride_comfort,
    )
    return node.base_prize * reliability * weather
