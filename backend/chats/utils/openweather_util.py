# openweather_util.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


class OpenWeatherError(Exception):
    """Raised when OpenWeather API requests fail."""


@dataclass
class WeatherResult:
    city: str
    country: str
    temperature: float
    feels_like: float
    description: str
    humidity: int
    wind_speed: float


class OpenWeatherClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        units: str = "metric",
        lang: str = "en",
        timeout: int = 15,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENWEATHER_API_KEY")
        if not self.api_key:
            raise ValueError("Missing OpenWeather API key. Set OPENWEATHER_API_KEY.")

        self.units = units
        self.lang = lang
        self.timeout = timeout

        self.base_weather_url = "https://api.openweathermap.org/data/2.5/weather"
        self.base_geo_url = "https://api.openweathermap.org/geo/1.0/direct"

    def _request(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        params = {**params, "appid": self.api_key}
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            raise OpenWeatherError(f"OpenWeather request failed: {exc}") from exc
        except ValueError as exc:
            raise OpenWeatherError("OpenWeather returned invalid JSON.") from exc

        # OpenWeather often returns JSON error payloads with a 'cod' field.
        if isinstance(data, dict) and str(data.get("cod", "")) not in ("200", "0"):
            raise OpenWeatherError(data.get("message", "OpenWeather API error"))

        return data

    def geocode_city(self, city: str, limit: int = 1) -> Dict[str, Any]:
        data = self._request(
            self.base_geo_url,
            {
                "q": city,
                "limit": limit,
            },
        )
        if not data:
            raise OpenWeatherError(f"No coordinates found for: {city}")
        return data[0]

    def get_current_weather_by_coords(self, lat: float, lon: float) -> WeatherResult:
        data = self._request(
            self.base_weather_url,
            {
                "lat": lat,
                "lon": lon,
                "units": self.units,
                "lang": self.lang,
            },
        )
        return self._parse_weather(data)

    def get_current_weather_by_city(self, city: str) -> WeatherResult:
        place = self.geocode_city(city)
        return self.get_current_weather_by_coords(place["lat"], place["lon"])

    def get_weather_text_for_chatbot(self, city: str) -> str:
        weather = self.get_current_weather_by_city(city)
        unit = "°C" if self.units == "metric" else "°F" if self.units == "imperial" else "K"

        return (
            f"Weather in {weather.city}, {weather.country}: "
            f"{weather.description}, {weather.temperature}{unit} "
            f"(feels like {weather.feels_like}{unit}), "
            f"humidity {weather.humidity}%, wind {weather.wind_speed} m/s."
        )

    def _parse_weather(self, data: Dict[str, Any]) -> WeatherResult:
        try:
            return WeatherResult(
                city=data["name"],
                country=data["sys"]["country"],
                temperature=float(data["main"]["temp"]),
                feels_like=float(data["main"]["feels_like"]),
                description=str(data["weather"][0]["description"]).capitalize(),
                humidity=int(data["main"]["humidity"]),
                wind_speed=float(data["wind"]["speed"]),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise OpenWeatherError("Unexpected weather response structure.") from exc

        