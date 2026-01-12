from __future__ import annotations

import os
import time
from typing import Any, Dict, Tuple

import requests

# Simple in-process cache (per city+units)
_CACHE: Dict[str, Tuple[Dict[str, Any], float]] = {}
_TTL_SECONDS = 15 * 60


def get_weather(city: str, units: str = "metric", force_refresh: bool = False) -> Dict[str, Any]:
    """Return real weather for a city.

    Output contract (stable for the frontend):
      - city
      - condition (short)
      - description
      - temp_c (always present if success)
      - temp_f (always present if success)
      - temp (alias for selected units)
      - units ("°C" or "°F")
      - source
      - fetched_at (epoch seconds)

    Notes:
      - Primary source: OpenWeatherMap
      - Caches for 15 minutes unless force_refresh is True
    """

    city = (city or "").strip() or "Rabat"
    units = (units or "metric").strip().lower()
    units = "imperial" if units.startswith("imp") else "metric"

    cache_key = f"{city.lower()}|{units}"
    now = time.time()
    if not force_refresh and cache_key in _CACHE:
        data, ts = _CACHE[cache_key]
        if now - ts < _TTL_SECONDS:
            return data

    # ---- OpenWeatherMap ----
    api_key = os.getenv("OPENWEATHER_API_KEY") or os.getenv("WEATHER_API_KEY")
    if not api_key:
        # Demo-friendly fallback: allow the app to run without any external key.
        # This keeps the outfit generation working for presentations.
        out: Dict[str, Any] = {
            "city": city,
            "condition": "clear",
            "description": "clear sky (mock)",
            "temp_c": 20.0,
            "temp_f": 68.0,
            "temp": 20.0 if units == "metric" else 68.0,
            "units": "°C" if units == "metric" else "°F",
            "source": "MockWeather",
            "fetched_at": int(now),
            "confidence": 0.4,
            "note": "No OPENWEATHER_API_KEY set; returning mock weather for demo.",
        }
        _CACHE[cache_key] = (out, now)
        return out

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": api_key, "units": units}

    r = requests.get(url, params=params, timeout=8)
    # Useful error when city is wrong
    if r.status_code == 404:
        raise ValueError(f"City not found: {city}")
    r.raise_for_status()
    j = r.json() or {}

    temp = float((j.get("main") or {}).get("temp"))
    # Sanity check
    if temp < -80 or temp > 80:
        raise ValueError("Invalid temperature range returned by API")

    # Normalize condition fields
    w0 = (j.get("weather") or [{}])[0] or {}
    condition = str(w0.get("main") or "").strip().lower() or "unknown"
    description = str(w0.get("description") or "").strip().lower() or condition

    if units == "metric":
        temp_c = temp
        temp_f = (temp_c * 9.0 / 5.0) + 32.0
        temp_display = temp_c
        unit_symbol = "°C"
    else:
        temp_f = temp
        temp_c = (temp_f - 32.0) * 5.0 / 9.0
        temp_display = temp_f
        unit_symbol = "°F"

    out: Dict[str, Any] = {
        "city": city,
        "condition": condition,
        "description": description,
        "temp_c": round(temp_c, 1),
        "temp_f": round(temp_f, 1),
        "temp": round(temp_display, 1),
        "units": unit_symbol,
        "source": "OpenWeatherMap",
        "fetched_at": int(now),
        # If we reached here, we trust it.
        "confidence": 1.0,
    }

    _CACHE[cache_key] = (out, now)
    return out

def get_detailed_weather_recommendations(weather: Dict) -> Dict:
    """Generate detailed clothing recommendations based on weather."""
    temp = weather.get("temp_c", 20)
    condition = weather.get("condition", "").lower()
    
    recommendations = {
        "layers": [],
        "materials": [],
        "colors": [],
        "avoid": []
    }
    
    if temp < 10:
        recommendations["layers"].extend(["thermal", "sweater", "coat"])
        recommendations["materials"].extend(["wool", "fleece", "down"])
        recommendations["colors"].extend(["dark", "neutral"])
        recommendations["avoid"].append("thin fabrics")
    
    elif temp > 25:
        recommendations["layers"].extend(["light top", "shorts"])
        recommendations["materials"].extend(["cotton", "linen"])
        recommendations["colors"].extend(["light", "pastel"])
        recommendations["avoid"].append("heavy fabrics")
    
    if "rain" in condition:
        recommendations["layers"].append("waterproof jacket")
        recommendations["materials"].append("water-resistant")
        recommendations["avoid"].append("suede")
    
    return recommendations