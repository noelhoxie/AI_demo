"""
Weather-based shipping delay forecast for US regions.
Uses Open-Meteo GFS/HRRR (no API key). Rule-based model maps forecast
precipitation, snow, and wind to estimated delay days per area.
"""
import logging
import time
from typing import Any, List, Optional

import requests

# Cache forecast for 15 minutes to avoid rate limits
_CACHE: Optional[List[dict]] = None
_CACHE_TIME: float = 0
_CACHE_TTL = 900  # seconds

# One representative point per state (approximate centroid) for forecast.
# Covers continental US + AK, HI, DC. Used to fetch weather and label map regions.
US_STATE_POINTS = [
    ("AL", "Alabama", 32.3182, -86.9023),
    ("AK", "Alaska", 64.8378, -147.7164),
    ("AZ", "Arizona", 34.0489, -111.0937),
    ("AR", "Arkansas", 34.7465, -92.2896),
    ("CA", "California", 36.7783, -119.4179),
    ("CO", "Colorado", 39.1130, -105.3111),
    ("CT", "Connecticut", 41.6032, -73.0877),
    ("DE", "Delaware", 38.9108, -75.5277),
    ("DC", "District of Columbia", 38.9072, -77.0369),
    ("FL", "Florida", 27.6648, -81.5158),
    ("GA", "Georgia", 32.1574, -82.9071),
    ("HI", "Hawaii", 19.8968, -155.5828),
    ("ID", "Idaho", 44.0682, -114.7420),
    ("IL", "Illinois", 40.6331, -89.3985),
    ("IN", "Indiana", 40.2672, -86.1349),
    ("IA", "Iowa", 41.8780, -93.0977),
    ("KS", "Kansas", 38.5266, -96.7265),
    ("KY", "Kentucky", 37.6681, -84.6701),
    ("LA", "Louisiana", 31.1695, -91.8678),
    ("ME", "Maine", 45.2538, -69.4455),
    ("MD", "Maryland", 39.0458, -76.6413),
    ("MA", "Massachusetts", 42.4072, -71.3824),
    ("MI", "Michigan", 43.3266, -84.5361),
    ("MN", "Minnesota", 46.7296, -94.6859),
    ("MS", "Mississippi", 32.3547, -89.3985),
    ("MO", "Missouri", 37.9643, -91.8318),
    ("MT", "Montana", 46.8797, -110.3626),
    ("NE", "Nebraska", 41.4925, -99.9018),
    ("NV", "Nevada", 38.8026, -116.4194),
    ("NH", "New Hampshire", 43.1939, -71.5724),
    ("NJ", "New Jersey", 40.0583, -74.4057),
    ("NM", "New Mexico", 34.5199, -105.8701),
    ("NY", "New York", 43.2994, -74.2179),
    ("NC", "North Carolina", 35.7596, -79.0193),
    ("ND", "North Dakota", 47.5515, -101.0020),
    ("OH", "Ohio", 40.4173, -82.9071),
    ("OK", "Oklahoma", 35.0078, -97.0929),
    ("OR", "Oregon", 43.8041, -120.5542),
    ("PA", "Pennsylvania", 41.2033, -77.1945),
    ("RI", "Rhode Island", 41.5801, -71.4774),
    ("SC", "South Carolina", 33.8361, -81.1637),
    ("SD", "South Dakota", 43.9695, -99.9018),
    ("TN", "Tennessee", 35.5175, -86.5804),
    ("TX", "Texas", 31.9686, -97.7506),
    ("UT", "Utah", 39.3210, -111.0937),
    ("VT", "Vermont", 44.5588, -72.5778),
    ("VA", "Virginia", 37.4316, -78.6569),
    ("WA", "Washington", 47.7511, -120.7401),
    ("WV", "West Virginia", 38.5976, -80.4549),
    ("WI", "Wisconsin", 43.7844, -88.7879),
    ("WY", "Wyoming", 43.0760, -107.2903),
]

OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"
# Forecast window (days) used to compute delay
FORECAST_DAYS = 7
# Max delay days we report per region
MAX_DELAY_DAYS = 7

log = logging.getLogger(__name__)


def _delay_from_daily(
    precip_mm: float,
    snow_mm: float,
    wind_kmh: float,
) -> float:
    """
    Map one day's weather to contribution to shipping delay (in days).
    Based on typical logistics impact: snow and ice > heavy rain > high wind.
    """
    delay = 0.0
    # Snow (mm): 10+ mm => ~1 day, 25+ => 2, 50+ => 3
    if snow_mm is not None and snow_mm > 0:
        if snow_mm >= 50:
            delay += 3.0
        elif snow_mm >= 25:
            delay += 2.0
        elif snow_mm >= 10:
            delay += 1.0
        else:
            delay += 0.5
    # Heavy rain (mm): 25+ => 0.5 day, 50+ => 1
    if precip_mm is not None and precip_mm > 0:
        if precip_mm >= 50:
            delay += 1.0
        elif precip_mm >= 25:
            delay += 0.5
    # High wind (km/h): 60+ => 0.25, 80+ => 0.5
    if wind_kmh is not None and wind_kmh >= 80:
        delay += 0.5
    elif wind_kmh is not None and wind_kmh >= 60:
        delay += 0.25
    return delay


def fetch_forecast_for_points() -> List[dict]:
    """
    Fetch 7-day daily forecast for all US state points from Open-Meteo (GFS).
    Returns list of dicts with keys: state_abbr, state_name, lat, lon, daily (list of daily data).
    """
    lats = [p[2] for p in US_STATE_POINTS]
    lons = [p[3] for p in US_STATE_POINTS]
    params = {
        "latitude": ",".join(str(x) for x in lats),
        "longitude": ",".join(str(x) for x in lons),
        "daily": "precipitation_sum,snowfall_sum,precipitation_hours,windspeed_10m_max",
        "forecast_days": FORECAST_DAYS,
        "timezone": "America/New_York",
        "models": "gfs_seamless",
    }
    try:
        r = requests.get(OPEN_METEO_BASE, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        log.exception("Open-Meteo request failed: %s", e)
        return []

    # Multi-location: API returns a list of objects (one per location), same structure as single.
    locations = data if isinstance(data, list) else [data]
    result = []
    for i, loc in enumerate(locations):
        if i >= len(US_STATE_POINTS):
            break
        abbr, name, lat, lon = US_STATE_POINTS[i][:4]
        daily = loc.get("daily") or {}
        dates = daily.get("time") or []
        precip = daily.get("precipitation_sum") or []
        snow_cm = daily.get("snowfall_sum") or []  # API returns cm
        wind = daily.get("windspeed_10m_max") or []
        days_list = []
        for d in range(max(len(dates), len(precip), len(snow_cm), len(wind))):
            s_cm = snow_cm[d] if d < len(snow_cm) else None
            days_list.append({
                "date": dates[d] if d < len(dates) else None,
                "precipitation_sum_mm": precip[d] if d < len(precip) else None,
                "snowfall_sum_mm": (s_cm * 10) if s_cm is not None else None,  # cm -> mm
                "windspeed_10m_max_kmh": wind[d] if d < len(wind) else None,
            })
        result.append({
            "state_abbr": abbr,
            "state_name": name,
            "lat": lat,
            "lon": lon,
            "daily": days_list,
        })
    return result


def compute_delay_per_region(forecast: List[dict]) -> List[dict]:
    """
    From forecast per state, compute estimated shipping delay days (0..MAX_DELAY_DAYS)
    and primary driver. Returns list of { state_abbr, state_name, delay_days, driver }.
    """
    out = []
    for loc in forecast:
        total_delay = 0.0
        drivers = []
        for day in loc.get("daily") or []:
            p = day.get("precipitation_sum_mm") or 0
            s = day.get("snowfall_sum_mm") or 0
            w = day.get("windspeed_10m_max_kmh") or 0
            d = _delay_from_daily(p, s, w)
            total_delay += d
            if s >= 10:
                drivers.append("snow")
            elif p >= 25:
                drivers.append("rain")
            elif w >= 60:
                drivers.append("wind")
        delay_days = min(MAX_DELAY_DAYS, int(round(total_delay)))
        driver = "snow" if "snow" in drivers else ("rain" if "rain" in drivers else ("wind" if "wind" in drivers else "clear"))
        out.append({
            "state_abbr": loc["state_abbr"],
            "state_name": loc["state_name"],
            "lat": loc["lat"],
            "lon": loc["lon"],
            "delay_days": delay_days,
            "driver": driver,
        })
    return out


def get_weather_delays() -> List[dict]:
    """
    Fetch GFS forecast for US state points and return delay forecast per region.
    Each item: state_abbr, state_name, lat, lon, delay_days, driver.
    Results are cached for 15 minutes.
    """
    global _CACHE, _CACHE_TIME
    now = time.time()
    if _CACHE is not None and (now - _CACHE_TIME) < _CACHE_TTL:
        return _CACHE
    forecast = fetch_forecast_for_points()
    if not forecast:
        return _CACHE or []
    _CACHE = compute_delay_per_region(forecast)
    _CACHE_TIME = now
    return _CACHE
