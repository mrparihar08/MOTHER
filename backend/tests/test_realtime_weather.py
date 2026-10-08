import pytest
from unittest.mock import MagicMock
from backend.chats.utils.openweather_util import (
    extract_weather_target,
    OpenWeatherClient,
    WeatherResult,
    format_weather_markdown,
)
from backend.chats.handlers.utility_handler import handle_utility_request
from backend.chats.chatbot import chatbot_reply


def test_extract_weather_target_generic_queries():
    assert extract_weather_target("aaj weather kaisa hai?") is None
    assert extract_weather_target("aaj ka mausam kaisa hai") is None
    assert extract_weather_target("mausam kaisa hai") is None
    assert extract_weather_target("aaj barish hogi kya") is None
    assert extract_weather_target("what is the weather today?") is None
    assert extract_weather_target("current temperature") is None
    assert extract_weather_target("yahan ka mausam kaisa hai") is None
    assert extract_weather_target("batao aaj ka temp") is None


def test_extract_weather_target_explicit_cities():
    assert extract_weather_target("weather in Mumbai") == "Mumbai"
    assert extract_weather_target("Mumbai ka mausam kaisa hai") == "Mumbai"
    assert extract_weather_target("Delhi me aaj weather kaisa h") == "Delhi"
    assert extract_weather_target("London ka temperature kitna hai") == "London"
    assert extract_weather_target("Jaipur weather") == "Jaipur"
    assert extract_weather_target("New York weather update") == "New York"
    assert extract_weather_target("San Francisco weather today") == "San Francisco"


def test_weather_client_realtime_coords():
    client = OpenWeatherClient()
    # Test with coordinates for Mumbai (19.0728, 72.8826)
    result = client.get_realtime_weather(lat=19.0728, lon=72.8826)
    assert isinstance(result, WeatherResult)
    assert result.temperature is not None
    assert result.humidity >= 0
    assert result.is_realtime_location is True
    assert "Mumbai" in result.city or "Maharashtra" in result.region or result.city != ""


def test_weather_client_explicit_city():
    client = OpenWeatherClient()
    result = client.get_realtime_weather(city="Jaipur")
    assert isinstance(result, WeatherResult)
    assert "Jaipur" in result.city
    assert result.is_realtime_location is False


def test_format_weather_markdown():
    res = WeatherResult(
        city="Mumbai",
        region="Maharashtra",
        country="India",
        temperature=31.5,
        feels_like=34.0,
        description="Partly Cloudy",
        humidity=65,
        wind_speed=12.0,
        icon="⛅",
        is_realtime_location=True,
    )
    md = format_weather_markdown(res)
    assert "Real-Time Weather Report" in md
    assert "Mumbai" in md
    assert "31.5°C" in md
    assert "65%" in md


def test_handle_utility_weather_with_coords():
    mock_db = MagicMock()
    mock_user = MagicMock(id=1, name="TestUser")
    res = handle_utility_request(
        message="aaj weather kaisa hai?",
        db=mock_db,
        current_user=mock_user,
        latitude=19.0728,
        longitude=72.8826,
    )
    assert res is not None
    assert res["type"] == "text"
    assert "°C" in res["content"]
    assert "Weather" in res["content"]


def test_chatbot_reply_weather_dispatch():
    mock_db = MagicMock()
    mock_user = MagicMock(id=1, name="TestUser")
    res = chatbot_reply(
        message="Mumbai ka mausam kaisa hai",
        db=mock_db,
        current_user=mock_user,
    )
    assert res is not None
    assert res["type"] == "text"
    assert "Mumbai" in res["content"]
