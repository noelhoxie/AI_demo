"""
Load fake customer orders and enrich with weather-delay risk by origin/destination state.
An order is at weather risk (may be late) if it passes through a state with forecasted delay:
origin (manufacturing) state or delivery (destination) state.
Provides delivery locations with coordinates for map point markers.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from weather_delays import get_weather_delays

log = logging.getLogger(__name__)

FAKE_ORDERS_PATH = Path(__file__).resolve().parent / "fake_orders.json"

# Origin (manufacturing) site_id -> (lat, lon) for map origin-destination lines
ORIGIN_COORDS: Dict[str, Tuple[float, float]] = {
    "MFG-01": (41.8781, -87.6298),   # Chicago
    "MFG-02": (32.7767, -96.7970),   # Dallas
    "MFG-03": (39.9526, -75.1652),   # Philadelphia
    "MFG-04": (33.7490, -84.3880),   # Atlanta
    "MFG-05": (34.0522, -118.2437),  # Los Angeles
    "MFG-06": (42.3314, -83.0458),   # Detroit
    "MFG-07": (33.4484, -112.0740),  # Phoenix
    "MFG-08": (47.6062, -122.3321),  # Seattle
}

# Approximate (lat, lon) for delivery cities used in fake orders (for map markers)
DELIVERY_CITY_COORDS: Dict[Tuple[str, str], Tuple[float, float]] = {
    ("New York", "NY"): (40.7128, -74.0060),
    ("Los Angeles", "CA"): (34.0522, -118.2437),
    ("Chicago", "IL"): (41.8781, -87.6298),
    ("Houston", "TX"): (29.7604, -95.3698),
    ("Phoenix", "AZ"): (33.4484, -112.0740),
    ("Philadelphia", "PA"): (39.9526, -75.1652),
    ("San Antonio", "TX"): (29.4241, -98.4936),
    ("San Diego", "CA"): (32.7157, -117.1611),
    ("Dallas", "TX"): (32.7767, -96.7970),
    ("San Jose", "CA"): (37.3382, -121.8863),
    ("Austin", "TX"): (30.2672, -97.7431),
    ("Jacksonville", "FL"): (30.3322, -81.6557),
    ("Fort Worth", "TX"): (32.7555, -97.3308),
    ("Columbus", "OH"): (39.9612, -82.9988),
    ("Charlotte", "NC"): (35.2271, -80.8431),
    ("Seattle", "WA"): (47.6062, -122.3321),
    ("Denver", "CO"): (39.7392, -104.9903),
    ("Boston", "MA"): (42.3601, -71.0589),
    ("Nashville", "TN"): (36.1627, -86.7816),
    ("Detroit", "MI"): (42.3314, -83.0458),
}


def get_orders_with_weather() -> List[Dict[str, Any]]:
    """
    Load fake_orders.json and add per-order weather risk from state-level delays.
    Returns list of orders with added keys:
      origin_delay_days, destination_delay_days, is_weather_risk, weather_risk_reason
    """
    delay_by_state: Dict[str, int] = {}
    for d in get_weather_delays():
        delay_by_state[d["state_abbr"]] = d["delay_days"]

    if not FAKE_ORDERS_PATH.exists():
        log.warning("Fake orders file not found: %s", FAKE_ORDERS_PATH)
        return []

    try:
        with open(FAKE_ORDERS_PATH) as f:
            orders = json.load(f)
    except Exception as e:
        log.exception("Failed to load fake orders: %s", e)
        return []

    result = []
    for o in orders:
        origin_state = (o.get("origin_state") or "").strip().upper()
        dest_state = (o.get("delivery_state") or "").strip().upper()
        origin_delay = delay_by_state.get(origin_state, 0)
        dest_delay = delay_by_state.get(dest_state, 0)
        is_risk = origin_delay > 0 or dest_delay > 0
        reasons = []
        if origin_delay > 0:
            reasons.append("origin %d day(s)" % origin_delay)
        if dest_delay > 0:
            reasons.append("destination %d day(s)" % dest_delay)
        result.append({
            **o,
            "origin_delay_days": origin_delay,
            "destination_delay_days": dest_delay,
            "is_weather_risk": is_risk,
            "weather_risk_reason": "; ".join(reasons) if reasons else None,
        })
    return result


def get_orders_by_state() -> Dict[str, List[Dict[str, Any]]]:
    """
    Orders (with weather fields) grouped by delivery_state.
    Keys are state abbreviations (e.g. "TX", "CA"); values are lists of order dicts.
    """
    orders = get_orders_with_weather()
    by_state: Dict[str, List[Dict[str, Any]]] = {}
    for o in orders:
        state = (o.get("delivery_state") or "").strip().upper()
        if not state:
            continue
        if state not in by_state:
            by_state[state] = []
        by_state[state].append(o)
    return by_state


def get_orders_by_zip() -> Dict[str, List[Dict[str, Any]]]:
    """
    Orders (with weather fields) grouped by delivery_zip.
    Keys are 5-digit zip strings; values are lists of order dicts.
    """
    orders = get_orders_with_weather()
    by_zip: Dict[str, List[Dict[str, Any]]] = {}
    for o in orders:
        z = (o.get("delivery_zip") or "").strip()
        if not z:
            continue
        if z not in by_zip:
            by_zip[z] = []
        by_zip[z].append(o)
    return by_zip


def get_delivery_locations() -> List[Dict[str, Any]]:
    """
    One row per delivery (city, state) with lat/lon and order count for map point markers.
    Includes list of orders for that location for drill-down.
    """
    orders = get_orders_with_weather()
    key_to_orders: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for o in orders:
        city = (o.get("delivery_city") or "").strip()
        state = (o.get("delivery_state") or "").strip().upper()
        if not city or not state:
            continue
        key = (city, state)
        if key not in key_to_orders:
            key_to_orders[key] = []
        key_to_orders[key].append(o)

    out: List[Dict[str, Any]] = []
    for (city, state), order_list in key_to_orders.items():
        coords = DELIVERY_CITY_COORDS.get((city, state))
        if coords is None:
            continue
        lat, lon = coords
        out.append({
            "delivery_city": city,
            "delivery_state": state,
            "lat": lat,
            "lon": lon,
            "order_count": len(order_list),
            "orders": order_list,
        })
    return out


def get_origin_destination_routes() -> List[Dict[str, Any]]:
    """
    One row per unique (origin_site_id, delivery city, delivery state) with coordinates
    for drawing origin-destination lines on the map. order_count and at_risk_count for styling.
    """
    orders = get_orders_with_weather()
    # key: (origin_site_id, delivery_city, delivery_state) -> list of orders
    key_to_orders: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for o in orders:
        site_id = (o.get("origin_site_id") or "").strip()
        city = (o.get("delivery_city") or "").strip()
        state = (o.get("delivery_state") or "").strip().upper()
        if not site_id or not city or not state:
            continue
        origin_coords = ORIGIN_COORDS.get(site_id)
        dest_coords = DELIVERY_CITY_COORDS.get((city, state))
        if origin_coords is None or dest_coords is None:
            continue
        key = (site_id, city, state)
        if key not in key_to_orders:
            key_to_orders[key] = []
        key_to_orders[key].append(o)

    out: List[Dict[str, Any]] = []
    for (site_id, city, state), order_list in key_to_orders.items():
        o_lat, o_lon = ORIGIN_COORDS[site_id]
        d_lat, d_lon = DELIVERY_CITY_COORDS[(city, state)]
        at_risk = sum(1 for o in order_list if o.get("is_weather_risk"))
        # Use first order for origin_name
        origin_name = (order_list[0].get("origin_name") or site_id) if order_list else site_id
        out.append({
            "origin_site_id": site_id,
            "origin_name": origin_name,
            "origin_lat": o_lat,
            "origin_lon": o_lon,
            "delivery_city": city,
            "delivery_state": state,
            "delivery_lat": d_lat,
            "delivery_lon": d_lon,
            "order_count": len(order_list),
            "at_risk_count": at_risk,
        })
    return out
