"""
Reroute suggestions for at-risk orders: find a closer manufacturing site with
same or better weather, and compute the capacity impact on that plant.
"""
import math
from typing import Any, Dict, List, Optional, Tuple

from orders_weather import get_orders_with_weather
from weather_delays import get_weather_delays

# Manufacturing sites: site_id -> (lat, lon) approximate city center
MFG_COORDS: Dict[str, Tuple[float, float]] = {
    "MFG-01": (41.88, -87.63),   # Chicago, IL
    "MFG-02": (32.78, -96.80),   # Dallas, TX
    "MFG-03": (39.95, -75.17),   # Philadelphia, PA
    "MFG-04": (33.75, -84.39),   # Atlanta, GA
    "MFG-05": (34.05, -118.25),  # Los Angeles, CA
    "MFG-06": (42.33, -83.05),   # Detroit, MI
    "MFG-07": (33.45, -112.07),  # Phoenix, AZ
    "MFG-08": (47.61, -122.33),  # Seattle, WA
}

# Delivery cities (city, state) -> (lat, lon)
DELIVERY_COORDS: Dict[Tuple[str, str], Tuple[float, float]] = {
    ("New York", "NY"): (40.71, -74.01),
    ("Los Angeles", "CA"): (34.05, -118.25),
    ("Chicago", "IL"): (41.88, -87.63),
    ("Houston", "TX"): (29.76, -95.37),
    ("Phoenix", "AZ"): (33.45, -112.07),
    ("Philadelphia", "PA"): (39.95, -75.17),
    ("San Antonio", "TX"): (29.42, -98.49),
    ("San Diego", "CA"): (32.72, -117.16),
    ("Dallas", "TX"): (32.78, -96.80),
    ("San Jose", "CA"): (37.34, -121.89),
    ("Austin", "TX"): (30.27, -97.74),
    ("Jacksonville", "FL"): (30.33, -81.66),
    ("Fort Worth", "TX"): (32.75, -97.33),
    ("Columbus", "OH"): (39.96, -83.00),
    ("Charlotte", "NC"): (35.23, -80.84),
    ("Seattle", "WA"): (47.61, -122.33),
    ("Denver", "CO"): (39.74, -104.99),
    ("Boston", "MA"): (42.36, -71.06),
    ("Nashville", "TN"): (36.16, -86.78),
    ("Detroit", "MI"): (42.33, -83.05),
}

# Site ID -> display name (match generate_fake_orders)
MFG_NAMES: Dict[str, str] = {
    "MFG-01": "Midwest Plant",
    "MFG-02": "South Central DC",
    "MFG-03": "Northeast Plant",
    "MFG-04": "Southeast Plant",
    "MFG-05": "West Coast DC",
    "MFG-06": "Great Lakes Plant",
    "MFG-07": "Southwest Plant",
    "MFG-08": "Pacific Northwest DC",
}


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in miles between two (lat, lon) points."""
    R = 3959  # Earth radius miles
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _current_load_and_capacity(orders: List[Dict[str, Any]]) -> Tuple[Dict[str, int], Dict[str, int]]:
    """From full order list, compute current load per site and capacity (current * 1.25, min headroom 20)."""
    load: Dict[str, int] = {sid: 0 for sid in MFG_COORDS}
    for o in orders:
        sid = o.get("origin_site_id")
        if sid in load:
            load[sid] += 1
    capacity = {
        sid: max(load[sid] + 20, int(load[sid] * 1.25))
        for sid in load
    }
    return load, capacity


def _dest_coords(order: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    city = (order.get("delivery_city") or "").strip()
    state = (order.get("delivery_state") or "").strip().upper()
    if not city or not state:
        return None
    key = (city, state)
    if key in DELIVERY_COORDS:
        return DELIVERY_COORDS[key]
    # Fallback: try (city, state) with original case for state
    for (c, s), coords in DELIVERY_COORDS.items():
        if c == city and s.upper() == state:
            return coords
    return None


def suggest_reroute(
    order: Dict[str, Any],
    delay_by_state: Dict[str, int],
    current_load: Dict[str, int],
    capacity: Dict[str, int],
) -> Optional[Dict[str, Any]]:
    """
    Suggest an alternate manufacturing site that is closer to destination and has
    same or better (lower) weather delay. Return reroute info and capacity impact.
    """
    origin_site = order.get("origin_site_id")
    origin_delay = order.get("origin_delay_days", 0)
    dest_coords = _dest_coords(order)
    if not dest_coords or not origin_site:
        return None
    dest_lat, dest_lon = dest_coords

    candidates: List[Tuple[str, float, int]] = []  # (site_id, distance_miles, delay_days)
    for sid, (lat, lon) in MFG_COORDS.items():
        if sid == origin_site:
            continue
        state_abbr = _site_state(sid)
        delay = delay_by_state.get(state_abbr, 0)
        dist = _haversine_miles(lat, lon, dest_lat, dest_lon)
        # Prefer same or better weather (delay <= origin_delay)
        if delay <= origin_delay:
            candidates.append((sid, dist, delay))
    if not candidates:
        return None
    # Closest first
    candidates.sort(key=lambda x: (x[1], x[2]))
    best_site, best_dist, best_delay = candidates[0]

    new_load = current_load.get(best_site, 0) + 1
    cap = capacity.get(best_site, new_load)
    util = round(100.0 * new_load / cap, 1) if cap else 0

    return {
        "reroute_site_id": best_site,
        "reroute_site_name": MFG_NAMES.get(best_site, best_site),
        "reroute_distance_miles": round(best_dist, 0),
        "reroute_origin_delay_days": best_delay,
        "reroute_plant_new_load": new_load,
        "reroute_plant_capacity": cap,
        "reroute_plant_utilization_pct": util,
        "reroute_reason": "Closer to destination, same or better weather",
    }


def _site_state(site_id: str) -> str:
    """Map site_id to state abbreviation for weather lookup."""
    mfg_states = {
        "MFG-01": "IL", "MFG-02": "TX", "MFG-03": "PA", "MFG-04": "GA",
        "MFG-05": "CA", "MFG-06": "MI", "MFG-07": "AZ", "MFG-08": "WA",
    }
    return mfg_states.get(site_id, "")


def get_orders_weather_alerts_with_reroute() -> List[Dict[str, Any]]:
    """
    At-risk orders (weather) enriched with reroute suggestion and capacity impact.
    Each order gets reroute_site_id, reroute_site_name, reroute_plant_new_load,
    reroute_plant_capacity, reroute_plant_utilization_pct, reroute_reason, etc.
    """
    orders = get_orders_with_weather()
    at_risk = [o for o in orders if o.get("is_weather_risk")]
    delay_by_state = {d["state_abbr"]: d["delay_days"] for d in get_weather_delays()}
    current_load, capacity = _current_load_and_capacity(orders)

    result = []
    for o in at_risk:
        row = dict(o)
        sug = suggest_reroute(o, delay_by_state, current_load, capacity)
        if sug:
            row.update(sug)
        else:
            row["reroute_site_id"] = None
            row["reroute_site_name"] = None
            row["reroute_plant_new_load"] = None
            row["reroute_plant_capacity"] = None
            row["reroute_plant_utilization_pct"] = None
            row["reroute_reason"] = "No closer plant with same or better weather"
        result.append(row)
    return result
