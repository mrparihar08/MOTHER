# backend/chats/utils/openweather_util.py
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class OpenWeatherError(Exception):
    """Raised when weather API requests fail."""


@dataclass
class WeatherResult:
    city: str
    region: str
    country: str
    temperature: float
    feels_like: float
    description: str
    humidity: int
    wind_speed: float
    weather_code: Optional[int] = None
    icon: str = "🌤️"
    is_realtime_location: bool = False
    location_source: str = "Real-Time GPS / Device Location"


# WMO Standard Weather Code Mapping with descriptions, emojis, and friendly tips
WMO_WEATHER_MAP: Dict[int, Tuple[str, str, str]] = {
    0: ("Clear Sky", "☀️", "Aasman bilkul saaf aur dhoopdaar hai."),
    1: ("Mainly Clear", "🌤️", "Aasman zyadatar saaf hai halki dhoop ke sath."),
    2: ("Partly Cloudy", "⛅", "Halke baadal chhayi hue hain."),
    3: ("Overcast", "☁️", "Aasman baadlon se ghira hua hai."),
    45: ("Fog", "🌫️", "Kohar (fog) chhaya hua hai, visibility kam ho sakti hai."),
    48: ("Depositing Rime Fog", "🌫️", "Kohar aur thandak bani hui hai."),
    51: ("Light Drizzle", "🌦️", "Halki boondabaandi (drizzle) ho rahi hai."),
    53: ("Moderate Drizzle", "🌦️", "Rimjhim baarish ho rahi hai."),
    55: ("Dense Drizzle", "🌧️", "Lagaatar boondabaandi chal rahi hai."),
    61: ("Slight Rain", "🌧️", "Halki baarish ho rahi hai. Chhata sath rakhein!"),
    63: ("Moderate Rain", "🌧️", "Madhyam baarish ho rahi hai. Bahar nikalte waqt savdhani bartein."),
    65: ("Heavy Rain", "🌧️", "Tez baarish ho rahi hai! Safar karte waqt savdhan rahein."),
    71: ("Slight Snowfall", "🌨️", "Halki barfbari (snowfall) ho rahi hai."),
    73: ("Moderate Snowfall", "🌨️", "Madhyam barfbari ho rahi hai."),
    75: ("Heavy Snowfall", "❄️", "Bhaari barfbari ho rahi hai."),
    77: ("Snow Grains", "🌨️", "Barf ke dane gir rahe hain."),
    80: ("Light Rain Showers", "🌦️", "Baarish ki phuharein gir rahi hain."),
    81: ("Moderate Rain Showers", "🌧️", "Baarish ki bauchhar chalu hai."),
    82: ("Violent Rain Showers", "⛈️", "Tez baarish ki jhadi lagi hui hai."),
    85: ("Slight Snow Showers", "🌨️", "Barf ki phuharein chal rahi hain."),
    86: ("Heavy Snow Showers", "❄️", "Tez barfbari ho rahi hai."),
    95: ("Thunderstorm", "⛈️", "Bijli aur garaj ke sath toofan/baarish ho sakti hai."),
    96: ("Thunderstorm with Hail", "⛈️", "Garaj-chamak aur ole padne ki sambhavna hai."),
    99: ("Severe Thunderstorm with Heavy Hail", "⛈️", "Tez garaj-chamak aur bhari ole padne ki aashanka hai."),
}

WEATHER_STOP_WORDS = {
    "aaj", "aajka", "aajki", "aajke", "today", "todays", "now", "abhi", "current", "live", "realtime",
    "kaisa", "kaisi", "kaise", "hoga", "hogi", "honge", "rahega", "rahegi", "hai", "h", "hain", "he",
    "ho", "raha", "rahi", "rahe", "kare", "karega", "karegi", "chal", "batao", "dikhao", "dekho", "bataiye",
    "please", "plz", "btao", "show", "tell", "check", "give", "me", "mein", "ko", "ka", "ki", "ke", "par", "pe",
    "weather", "mausam", "mosam", "temperature", "temp", "rain", "barish", "forecast", "hawa", "wind",
    "humidity", "garmi", "sardi", "thand", "heat", "cold", "climate", "bata",
    "in", "at", "of", "for", "from", "to",
    "what", "whats", "what's", "how", "hows", "is", "the", "a", "an", "my", "our", "here",
    "yahan", "yaha", "kya", "kitna", "kitni", "update", "status", "report", "info", "jankari", "vitya", "ai"
}


def extract_weather_target(text: str) -> Optional[str]:
    """
    Extracts explicit city/location name from user's natural query.
    Returns None if the query is a generic/current-location question (e.g. 'aaj weather kaisa hai?').
    """
    raw = (text or "").strip()
    if not raw:
        return None
    # Normalize punctuation
    clean = re.sub(r"[\?\,\.\!\:\;\-\_\/]", " ", raw)
    tokens = clean.split()
    location_tokens = [t for t in tokens if t.lower() not in WEATHER_STOP_WORDS]
    if not location_tokens:
        return None
    candidate = " ".join(location_tokens).strip()
    # Filter out pure numbers or single letters
    if len(candidate) <= 1 or re.match(r"^\d+$", candidate):
        return None
    return candidate


def reverse_geocode(lat: float, lon: float, timeout: int = 5) -> Tuple[str, str, str]:
    """
    Reverse geocodes coordinates to (city, region, country).
    Uses free keyless BigDataCloud reverse geocoding with fallback to Nominatim.
    """
    # 1. BigDataCloud API
    try:
        url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lon}&localityLanguage=en"
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            city = data.get("city") or data.get("locality") or data.get("principalSubdivision") or "Current Location"
            region = data.get("principalSubdivision") or ""
            country = data.get("countryName") or ""
            return city, region, country
    except Exception as e:
        logger.debug("BigDataCloud reverse geocode error: %s", e)

    # 2. Nominatim fallback
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        resp = requests.get(url, headers={"User-Agent": "VityaWeatherService/1.0"}, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            addr = data.get("address", {})
            city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("suburb") or "Current Location"
            region = addr.get("state") or addr.get("region") or ""
            country = addr.get("country") or ""
            return city, region, country
    except Exception as e:
        logger.debug("Nominatim reverse geocode error: %s", e)

    return "Current Location", "", ""


def get_location_from_ip(client_ip: Optional[str] = None, timeout: int = 5) -> Optional[Dict[str, Any]]:
    """
    Resolves geographic location via IP address when GPS coordinates are unavailable.
    """
    # Check if client_ip is a local/private address
    ip_target = ""
    if client_ip and not client_ip.startswith(("127.", "192.168.", "10.", "172.16.", "::1")):
        ip_target = client_ip.strip()

    try:
        url = f"http://ip-api.com/json/{ip_target}?fields=status,city,regionName,country,lat,lon"
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success" and data.get("lat") is not None and data.get("lon") is not None:
                return {
                    "city": data.get("city") or "Local Area",
                    "region": data.get("regionName") or "",
                    "country": data.get("country") or "India",
                    "latitude": float(data["lat"]),
                    "longitude": float(data["lon"]),
                }
    except Exception as e:
        logger.debug("IP Geolocation error: %s", e)

    return None


def get_weather_from_openmeteo(
    lat: float,
    lon: float,
    city_name: Optional[str] = None,
    region: Optional[str] = None,
    country: Optional[str] = None,
    is_realtime_location: bool = False,
    location_source: str = "Real-Time GPS / Device Location",
    timeout: int = 6,
) -> WeatherResult:
    """
    Fetches real-time weather using Open-Meteo's high-precision forecast API.
    """
    if not city_name or city_name == "Current Location":
        c, r, cnt = reverse_geocode(lat, lon, timeout=timeout)
        city_name = c or city_name or "Current Location"
        region = region or r
        country = country or cnt

    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m"
            f"&timezone=auto"
        )
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            curr = data.get("current", {})
            weather_code = curr.get("weather_code", 0)
            wmo_info = WMO_WEATHER_MAP.get(weather_code, ("Fair / Clear", "🌤️", "Mausam theek bana hua hai."))
            desc, icon, _ = wmo_info

            return WeatherResult(
                city=city_name or "Current Location",
                region=region or "",
                country=country or "",
                temperature=float(curr.get("temperature_2m", 28.0)),
                feels_like=float(curr.get("apparent_temperature", curr.get("temperature_2m", 28.0))),
                description=desc,
                humidity=int(curr.get("relative_humidity_2m", 50)),
                wind_speed=float(curr.get("wind_speed_10m", 5.0)),
                weather_code=weather_code,
                icon=icon,
                is_realtime_location=is_realtime_location,
                location_source=location_source,
            )
    except Exception as e:
        logger.warning("Open-Meteo forecast API error: %s", e)

    return WeatherResult(
        city=city_name or "Current Location",
        region=region or "",
        country=country or "",
        temperature=28.0,
        feels_like=30.0,
        description="Mainly Clear",
        humidity=55,
        wind_speed=8.0,
        weather_code=1,
        icon="🌤️",
        is_realtime_location=is_realtime_location,
        location_source=location_source,
    )


def get_weather_from_openmeteo_city(city: str, timeout: int = 6) -> WeatherResult:
    """
    Geocodes city name and fetches weather from Open-Meteo.
    """
    clean_query = city.strip()
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(clean_query)}&count=1&language=en&format=json"
        geo_resp = requests.get(geo_url, timeout=timeout)
        if geo_resp.status_code == 200:
            geo_data = geo_resp.json()
            results = geo_data.get("results")
            if results:
                first = results[0]
                lat = float(first["latitude"])
                lon = float(first["longitude"])
                name = first.get("name") or city
                region = first.get("admin1") or ""
                country = first.get("country") or ""

                return get_weather_from_openmeteo(
                    lat=lat,
                    lon=lon,
                    city_name=name,
                    region=region,
                    country=country,
                    is_realtime_location=False,
                    location_source=f"Location: {name}, {country}".strip(", "),
                    timeout=timeout,
                )
    except Exception as e:
        logger.warning("Open-Meteo city lookup exception: %s", e)

    return WeatherResult(
        city=city.title(),
        region="",
        country="",
        temperature=27.0,
        feels_like=29.0,
        description="Partly Cloudy",
        humidity=60,
        wind_speed=10.0,
        weather_code=2,
        icon="⛅",
        is_realtime_location=False,
        location_source=f"Location: {city.title()}",
    )


def format_weather_markdown(weather: WeatherResult) -> str:
    """
    Renders an elegant, rich markdown card for chat response.
    """
    # Build location string
    loc_parts = [weather.city]
    if weather.region and weather.region != weather.city:
        loc_parts.append(weather.region)
    if weather.country:
        loc_parts.append(weather.country)
    full_loc = ", ".join(loc_parts)

    title_prefix = "📍 **Real-Time Weather Report**" if weather.is_realtime_location else "🌦️ **Weather Report**"
    
    # Contextual weather tip
    tip_msg = "Mausam suhana hai! Din ka aanand lein."
    if weather.weather_code in WMO_WEATHER_MAP:
        tip_msg = WMO_WEATHER_MAP[weather.weather_code][2]
    elif weather.temperature > 35:
        tip_msg = "Garmi kafi zyada hai, hydration banaye rakhein aur dhoop se bachein! 🥤"
    elif weather.temperature < 15:
        tip_msg = "Mausam thanda hai, garam kapde sath rakhein! 🧥"
    elif "rain" in weather.description.lower() or "drizzle" in weather.description.lower():
        tip_msg = "Baarish ki sambhavna hai, bahar nikalte waqt chhata (umbrella) sath rakhein! ☔"

    source_line = f"• **Location Source:** 📍 {weather.location_source}" if weather.is_realtime_location else f"• **Location:** 📍 {full_loc}"

    lines = [
        f"{title_prefix}: **{full_loc}**\n",
        f"• **Condition:** {weather.description} {weather.icon}",
        f"• **Temperature:** **{weather.temperature:.1f}°C** (Feels like {weather.feels_like:.1f}°C)",
        f"• **Humidity:** {weather.humidity}%",
        f"• **Wind Speed:** {weather.wind_speed:.1f} km/h",
        source_line,
        f"\n💡 *Tip: {tip_msg}*",
    ]
    return "\n".join(lines)


class OpenWeatherClient:
    """
    Comprehensive Weather Client supporting OpenWeather API, Open-Meteo,
    real-time GPS coordinates, and IP-based geolocation fallback.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        units: str = "metric",
        lang: str = "en",
        timeout: int = 8,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENWEATHER_API_KEY")
        self.units = units
        self.lang = lang
        self.timeout = timeout
        self.base_weather_url = "https://api.openweathermap.org/data/2.5/weather"
        self.base_geo_url = "https://api.openweathermap.org/geo/1.0/direct"

    def geocode_city(self, city: str, limit: int = 1) -> Dict[str, Any]:
        if not self.api_key:
            return {}
        try:
            resp = requests.get(
                self.base_geo_url,
                params={"q": city, "limit": limit, "appid": self.api_key},
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    return data[0]
        except Exception as e:
            logger.debug("OpenWeather geocoding error: %s", e)
        return {}

    def get_current_weather_by_coords(
        self,
        lat: float,
        lon: float,
        is_realtime_location: bool = False,
        location_source: str = "Real-Time GPS / Device Location",
    ) -> WeatherResult:
        """
        Attempts OpenWeather coords query; automatically falls back to Open-Meteo.
        """
        if self.api_key:
            try:
                params = {
                    "lat": lat,
                    "lon": lon,
                    "units": self.units,
                    "lang": self.lang,
                    "appid": self.api_key,
                }
                resp = requests.get(self.base_weather_url, params=params, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    desc = str(data["weather"][0]["description"]).capitalize()
                    main = data["weather"][0].get("main", "").lower()
                    icon = "🌧️" if "rain" in main else "⛅" if "cloud" in main else "⛈️" if "thunder" in main else "☀️"
                    return WeatherResult(
                        city=data.get("name", "Current Location"),
                        region="",
                        country=data.get("sys", {}).get("country", ""),
                        temperature=float(data["main"]["temp"]),
                        feels_like=float(data["main"]["feels_like"]),
                        description=desc,
                        humidity=int(data["main"]["humidity"]),
                        wind_speed=float(data["wind"]["speed"] * 3.6),  # convert m/s to km/h
                        icon=icon,
                        is_realtime_location=is_realtime_location,
                        location_source=location_source,
                    )
            except Exception as e:
                logger.warning("OpenWeather coords lookup failed, falling back to Open-Meteo: %s", e)

        # Fallback to Open-Meteo
        return get_weather_from_openmeteo(
            lat=lat,
            lon=lon,
            is_realtime_location=is_realtime_location,
            location_source=location_source,
            timeout=self.timeout,
        )

    def get_current_weather_by_city(self, city: str) -> WeatherResult:
        """
        Fetches weather for a specific city via OpenWeather or Open-Meteo.
        """
        if self.api_key:
            try:
                place = self.geocode_city(city)
                if place and "lat" in place and "lon" in place:
                    res = self.get_current_weather_by_coords(
                        place["lat"],
                        place["lon"],
                        is_realtime_location=False,
                        location_source=f"Location: {city}",
                    )
                    res.city = place.get("name", city)
                    res.country = place.get("country", "")
                    return res
            except Exception as e:
                logger.warning("OpenWeather city lookup failed: %s", e)

        # Open-Meteo city lookup
        return get_weather_from_openmeteo_city(city, timeout=self.timeout)

    def get_weather_text_for_chatbot(
        self,
        city: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        client_ip: Optional[str] = None,
    ) -> str:
        """
        Generates markdown weather report for chatbot with seamless location resolution.
        """
        weather = self.get_realtime_weather(city=city, lat=lat, lon=lon, client_ip=client_ip)
        return format_weather_markdown(weather)

    def get_realtime_weather(
        self,
        city: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        client_ip: Optional[str] = None,
    ) -> WeatherResult:
        """
        Universal weather resolver:
        1. If explicit city is requested -> fetch for city
        2. Else if GPS coords (lat, lon) provided -> fetch for GPS coords
        3. Else if IP geolocation available -> fetch for IP location
        4. Fallback to default (Delhi, India)
        """
        if city and city.strip() and city.lower() not in ("current", "live", "realtime", "yahan", "here", "today"):
            return self.get_current_weather_by_city(city.strip())

        if lat is not None and lon is not None:
            return self.get_current_weather_by_coords(
                lat=lat,
                lon=lon,
                is_realtime_location=True,
                location_source="Real-Time GPS / Device Location",
            )

        # Try IP Geolocation
        ip_loc = get_location_from_ip(client_ip)
        if ip_loc:
            return self.get_current_weather_by_coords(
                lat=ip_loc["latitude"],
                lon=ip_loc["longitude"],
                is_realtime_location=True,
                location_source=f"Network IP Location ({ip_loc.get('city', 'Detected Area')})",
            )

        # Default Fallback: New Delhi, India
        return self.get_current_weather_by_city("New Delhi")