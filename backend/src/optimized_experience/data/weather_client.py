"""Hourly weather forecast access via the US National Weather Service API
(api.weather.gov) — free, no API key, requires only a descriptive User-Agent.
Used to reason about water-ride comfort (temperature + sky condition).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel

from optimized_experience.data.cache import InProcessTTLCache

NWS_BASE_URL = "https://api.weather.gov"

# Disneyland Park, Anaheim CA.
DISNEYLAND_LATITUDE = 33.8121
DISNEYLAND_LONGITUDE = -117.9190

_FORECAST_TTL_SECONDS = 1800


class HourlyWeather(BaseModel):
    hour: datetime
    temperature_f: float
    short_forecast: str


class WeatherSource(Protocol):
    def get_hourly_forecast(self) -> list[HourlyWeather]: ...


class NWSWeatherSource:
    """Real HTTP client against api.weather.gov for a fixed lat/lon."""

    def __init__(
        self,
        latitude: float = DISNEYLAND_LATITUDE,
        longitude: float = DISNEYLAND_LONGITUDE,
        contact: str = "optimized-experience@example.com",
        timeout_seconds: float = 20.0,
    ) -> None:
        self._latitude = latitude
        self._longitude = longitude
        self._client = httpx.Client(
            base_url=NWS_BASE_URL,
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": f"OptimizedExperience/0.1 (contact: {contact})"},
        )
        self._cache = InProcessTTLCache(ttl_seconds=_FORECAST_TTL_SECONDS)
        self._hourly_forecast_url: str | None = None

    def _resolve_hourly_forecast_url(self) -> str:
        if self._hourly_forecast_url is None:
            points = self._client.get(f"/points/{self._latitude},{self._longitude}")
            points.raise_for_status()
            self._hourly_forecast_url = points.json()["properties"]["forecastHourly"]
        return self._hourly_forecast_url

    def get_hourly_forecast(self) -> list[HourlyWeather]:
        return self._cache.get_or_set("hourly_forecast", self._fetch_hourly_forecast)

    def _fetch_hourly_forecast(self) -> list[HourlyWeather]:
        url = self._resolve_hourly_forecast_url()
        response = self._client.get(url)
        response.raise_for_status()
        periods = response.json()["properties"]["periods"]
        return [
            HourlyWeather(
                hour=period["startTime"],
                temperature_f=period["temperature"],
                short_forecast=period["shortForecast"],
            )
            for period in periods
        ]

    def close(self) -> None:
        self._client.close()


class ReplayWeatherSource:
    """Fixture-backed WeatherSource for offline demos and tests.

    Expects `weather_hourly.json` with the same shape as NWS's
    `.../forecast/hourly` response (`properties.periods[...]`).
    """

    def __init__(self, fixture_path: Path) -> None:
        self._fixture_path = fixture_path

    def get_hourly_forecast(self) -> list[HourlyWeather]:
        data = json.loads(self._fixture_path.read_text())
        periods = data["properties"]["periods"]
        return [
            HourlyWeather(
                hour=period["startTime"],
                temperature_f=period["temperature"],
                short_forecast=period["shortForecast"],
            )
            for period in periods
        ]
