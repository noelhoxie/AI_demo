"""
Weather conditions (delay forecast) by zip-code-level granularity.
Uses a grid of US locations with zip-style IDs; fetches Open-Meteo for each point.
"""
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from weather_delays import (
    OPEN_METEO_BASE,
    FORECAST_DAYS,
    MAX_DELAY_DAYS,
    _delay_from_daily,
    log,
)

# Grid of (zip_id, lat, lon) for continental US + AK/HI. ~400 points at ~1.2° spacing.
# zip_id is 5-digit style for display (10001, 10002, ...).
def _build_zip_grid() -> List[Tuple[str, float, float]]:
    out = []
    idx = 10001
    # Continental US: lat 25-49, lon -125 to -66
    lat_step = 1.2
    lon_step = 1.5
    lat = 25.0
    while lat <= 49.0:
        lon = -125.0
        while lon <= -66.0:
            out.append((str(idx), round(lat, 2), round(lon, 2)))
            idx += 1
            lon += lon_step
        lat += lat_step
    # Alaska (few points)
    for lat, lon in [(64.0, -149.0), (64.0, -157.0), (58.0, -134.0)]:
        out.append((str(idx), lat, lon))
        idx += 1
    # Hawaii (few points)
    for lat, lon in [(21.3, -157.8), (20.0, -155.5)]:
        out.append((str(idx), lat, lon))
        idx += 1
    return out


ZIP_GRID: List[Tuple[str, float, float]] = _build_zip_grid()

_ZIP_CACHE: Optional[List[Dict[str, Any]]] = None
_ZIP_CACHE_TIME: float = 0
_ZIP_CACHE_TTL = 900  # 15 min


# Max locations per request to avoid 414 URI Too Long (URL length limit)
_BATCH_SIZE = 100
# Pause between batches to avoid 429 Too Many Requests (Open-Meteo ~600/min)
_BATCH_DELAY_SEC = 1.5


def fetch_forecast_for_zip_points() -> List[Dict[str, Any]]:
    """Fetch Open-Meteo 7-day daily forecast for all zip grid points (batched to avoid 414)."""
    points = ZIP_GRID[:1000] if len(ZIP_GRID) > 1000 else ZIP_GRID
    result = []
    for start in range(0, len(points), _BATCH_SIZE):
        if start > 0:
            time.sleep(_BATCH_DELAY_SEC)
        batch = points[start : start + _BATCH_SIZE]
        lats = [p[1] for p in batch]
        lons = [p[2] for p in batch]
        params = {
            "latitude": ",".join(str(x) for x in lats),
            "longitude": ",".join(str(x) for x in lons),
            "daily": "precipitation_sum,snowfall_sum,precipitation_hours,windspeed_10m_max",
            "forecast_days": FORECAST_DAYS,
            "timezone": "America/New_York",
            "models": "gfs_seamless",
        }
        try:
            r = requests.get(OPEN_METEO_BASE, params=params, timeout=45)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            log.warning("Open-Meteo zip batch failed (start=%d): %s", start, e)
            continue
        locations = data if isinstance(data, list) else [data]
        for i, loc in enumerate(locations):
            if i >= len(batch):
                break
            zip_id, lat, lon = batch[i]
            daily = loc.get("daily") or {}
            dates = daily.get("time") or []
            precip = daily.get("precipitation_sum") or []
            snow_cm = daily.get("snowfall_sum") or []
            wind = daily.get("windspeed_10m_max") or []
            days_list = []
            for d in range(max(len(dates), len(precip), len(snow_cm), len(wind))):
                s_cm = snow_cm[d] if d < len(snow_cm) else None
                days_list.append({
                    "precipitation_sum_mm": precip[d] if d < len(precip) else None,
                    "snowfall_sum_mm": (s_cm * 10) if s_cm is not None else None,
                    "windspeed_10m_max_kmh": wind[d] if d < len(wind) else None,
                })
            result.append({
                "zip": zip_id,
                "lat": lat,
                "lon": lon,
                "daily": days_list,
            })
    return result


def compute_delay_per_zip(forecast: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compute delay_days and driver per zip from forecast."""
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
            "zip": loc["zip"],
            "lat": loc["lat"],
            "lon": loc["lon"],
            "delay_days": delay_days,
            "driver": driver,
        })
    return out


def get_weather_by_zip() -> List[Dict[str, Any]]:
    """
    Weather conditions (delay forecast) by zip-level grid.
    Returns list of { zip, lat, lon, delay_days, driver }. Cached 15 min.
    """
    global _ZIP_CACHE, _ZIP_CACHE_TIME
    now = time.time()
    if _ZIP_CACHE is not None and (now - _ZIP_CACHE_TIME) < _ZIP_CACHE_TTL:
        return _ZIP_CACHE
    forecast = fetch_forecast_for_zip_points()
    if not forecast:
        return _ZIP_CACHE or []
    _ZIP_CACHE = compute_delay_per_zip(forecast)
    _ZIP_CACHE_TIME = now
    return _ZIP_CACHE
