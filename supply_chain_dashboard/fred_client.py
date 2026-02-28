"""
Federal Reserve Economic Data (FRED) API client.
Used by Demand tab (search public FRED series) and Forecasting tab (fetch series for models).
"""
import logging
from typing import Any, Optional
import requests

from config import FRED_API_KEY, FRED_BASE_URL

log = logging.getLogger(__name__)


def _get(path: str, params: Optional[dict] = None) -> dict:
    p = dict(params or {})
    p.setdefault("file_type", "json")
    if FRED_API_KEY:
        p["api_key"] = FRED_API_KEY
    url = f"{FRED_BASE_URL}/{path}"
    try:
        r = requests.get(url, params=p, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        log.warning("FRED request failed: %s", e)
        raise


def search_series(search_text: str, limit: int = 50) -> list[dict[str, Any]]:
    """Search FRED for economic data series. Returns list of series dicts (id, title, frequency, units, etc.)."""
    if not search_text or not search_text.strip():
        return []
    data = _get("series/search", {"search_text": search_text.strip(), "limit": min(limit, 1000)})
    return data.get("seriess", [])


def get_observations(
    series_id: str,
    observation_start: Optional[str] = None,
    observation_end: Optional[str] = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    """Get observations (date, value) for a FRED series. Dates in YYYY-MM-DD."""
    params = {"series_id": series_id, "limit": limit}
    if observation_start:
        params["observation_start"] = observation_start
    if observation_end:
        params["observation_end"] = observation_end
    data = _get("series/observations", params)
    return data.get("observations", [])
