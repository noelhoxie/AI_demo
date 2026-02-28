"""
Supply chain disruption simulator.

Takes baseline SAP-style data and applies configurable disruptions (supplier delay,
plant outage, logistics delay, demand spike, inventory shortage). Returns a deep
copy of the data with disruptions applied so the control tower can show "what-if" views.
"""
import copy
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _parse_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _apply_supplier_delay(
    procurement: List[Dict[str, Any]],
    severity: str,
    scope_vendor: Optional[str],
) -> List[Dict[str, Any]]:
    """Delay delivery dates and set some POs to Overdue. Optionally limit to one vendor."""
    out = copy.deepcopy(procurement)
    days_delay = {"low": 3, "medium": 7, "high": 14}.get(severity, 7)
    overdue_ratio = {"low": 0.1, "medium": 0.25, "high": 0.5}.get(severity, 0.25)

    for r in out:
        if scope_vendor and r.get("vendor") != scope_vendor:
            continue
        if r.get("status") in ("Delivered",):
            continue
        d = _parse_date(r.get("delivery", ""))
        if d:
            d = d + timedelta(days=days_delay)
            r["delivery"] = _date_str(d)
            if random.random() < overdue_ratio:
                r["status"] = "Overdue"
    return out


def _apply_plant_outage(
    manufacturing: List[Dict[str, Any]],
    inventory: List[Dict[str, Any]],
    severity: str,
    scope_plant: Optional[str],
) -> tuple:
    """Delay or cancel manufacturing at a plant; reduce inventory at that plant."""
    mfg_out = copy.deepcopy(manufacturing)
    inv_out = copy.deepcopy(inventory)

    days_delay = {"low": 5, "medium": 10, "high": 21}.get(severity, 10)
    cancel_ratio = {"low": 0, "medium": 0.15, "high": 0.35}.get(severity, 0.15)
    inventory_cut = {"low": 0.2, "medium": 0.5, "high": 0.8}.get(severity, 0.5)

    for r in mfg_out:
        plant = r.get("plant", "")
        if scope_plant and plant != scope_plant:
            continue
        if r.get("status") == "Completed":
            continue
        if random.random() < cancel_ratio:
            r["status"] = "Cancelled"
        else:
            for key in ("start", "end"):
                d = _parse_date(r.get(key, ""))
                if d:
                    r[key] = _date_str(d + timedelta(days=days_delay))

    for r in inv_out:
        if scope_plant and r.get("plant") != scope_plant:
            continue
        u = r.get("unrestricted", 0)
        r["unrestricted"] = max(0, int(u * (1 - inventory_cut)))
        r["blocked"] = (r.get("blocked") or 0) + int(u * inventory_cut)

    return mfg_out, inv_out


def _apply_logistics_delay(
    logistics: List[Dict[str, Any]],
    severity: str,
    scope_carrier: Optional[str],
) -> List[Dict[str, Any]]:
    """Push out planned dates and move some to Pending/In Transit."""
    out = copy.deepcopy(logistics)
    days_delay = {"low": 2, "medium": 5, "high": 10}.get(severity, 5)
    to_pending_ratio = {"low": 0.1, "medium": 0.3, "high": 0.5}.get(severity, 0.3)

    for r in out:
        if scope_carrier and r.get("carrier") != scope_carrier:
            continue
        d = _parse_date(r.get("planned", ""))
        if d:
            r["planned"] = _date_str(d + timedelta(days=days_delay))
        if r.get("status") == "Delivered":
            continue
        if random.random() < to_pending_ratio:
            r["status"] = "Pending"
        else:
            r["status"] = "In Transit"
    return out


def _apply_demand_spike(
    demand: List[Dict[str, Any]],
    severity: str,
    scope_customer: Optional[str],
) -> List[Dict[str, Any]]:
    """Increase quantities on open/confirmed orders; optionally add extra demand."""
    out = copy.deepcopy(demand)
    multiplier = {"low": 1.15, "medium": 1.35, "high": 1.6}.get(severity, 1.35)
    extra_orders = {"low": 0, "medium": 2, "high": 5}.get(severity, 2)

    for r in out:
        if scope_customer and r.get("customer") != scope_customer:
            continue
        r["qty"] = int((r.get("qty") or 0) * multiplier)
        r["forecastQty"] = int((r.get("forecastQty") or 0) * multiplier)

    base_date = datetime.now()
    for _ in range(extra_orders):
        out.append({
            "order": str(200000 + random.randint(1, 99999)),
            "customer": scope_customer or f"CUST-{random.choice('ABCD')}{random.randint(100, 500):03d}",
            "material": f"FG-90{random.randint(1, 7):02d}",
            "qty": random.randint(100, 400),
            "requestDate": _date_str(base_date + timedelta(days=random.randint(7, 45))),
            "status": "Open",
            "forecastQty": random.randint(80, 450),
        })
    return out


def _apply_inventory_shortage(
    inventory: List[Dict[str, Any]],
    severity: str,
    scope_plant: Optional[str],
) -> List[Dict[str, Any]]:
    """Reduce unrestricted stock and/or increase blocked; optionally by plant."""
    out = copy.deepcopy(inventory)
    cut = {"low": 0.15, "medium": 0.35, "high": 0.55}.get(severity, 0.35)
    block_ratio = {"low": 0.2, "medium": 0.4, "high": 0.6}.get(severity, 0.4)

    for r in out:
        if scope_plant and r.get("plant") != scope_plant:
            continue
        u = r.get("unrestricted", 0)
        to_block = int(u * cut * block_ratio)
        to_remove = int(u * cut * (1 - block_ratio))
        r["unrestricted"] = max(0, u - to_block - to_remove)
        r["blocked"] = (r.get("blocked") or 0) + to_block
    return out


def run_simulation(
    sap_data: Dict[str, List[Dict[str, Any]]],
    disruptions: List[Dict[str, Any]],
    seed: Optional[int] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Apply a list of disruptions to a copy of sap_data and return the result.

    Args:
        sap_data: Full SAP-style dict (procurement, inventory, manufacturing, logistics, demand).
        disruptions: List of {"type": str, "severity": "low"|"medium"|"high", "scope": str|null}.
            type: "supplier_delay" | "plant_outage" | "logistics_delay" | "demand_spike" | "inventory_shortage"
            scope: optional vendor id, plant id, carrier name, or customer id depending on type.
        seed: Random seed for reproducible runs.

    Returns:
        New dict with same keys; data is deep-copied and modified.
    """
    if seed is not None:
        random.seed(seed)

    result = {
        "procurement": copy.deepcopy(sap_data.get("procurement", [])),
        "inventory": copy.deepcopy(sap_data.get("inventory", [])),
        "manufacturing": copy.deepcopy(sap_data.get("manufacturing", [])),
        "logistics": copy.deepcopy(sap_data.get("logistics", [])),
        "demand": copy.deepcopy(sap_data.get("demand", [])),
    }

    for d in disruptions:
        dtype = (d.get("type") or "").strip().lower()
        severity = (d.get("severity") or "medium").strip().lower()
        scope = d.get("scope") or None
        if isinstance(scope, str):
            scope = scope.strip() or None

        if dtype == "supplier_delay":
            result["procurement"] = _apply_supplier_delay(
                result["procurement"], severity, scope
            )
        elif dtype == "plant_outage":
            result["manufacturing"], result["inventory"] = _apply_plant_outage(
                result["manufacturing"], result["inventory"], severity, scope
            )
        elif dtype == "logistics_delay":
            result["logistics"] = _apply_logistics_delay(
                result["logistics"], severity, scope
            )
        elif dtype == "demand_spike":
            result["demand"] = _apply_demand_spike(
                result["demand"], severity, scope
            )
        elif dtype == "inventory_shortage":
            result["inventory"] = _apply_inventory_shortage(
                result["inventory"], severity, scope
            )

    return result
