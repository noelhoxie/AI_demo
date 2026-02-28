"""
Dashboard-level disruption simulator.

Takes the same payload shape as the dashboard APIs (KPIs + chart data) and applies
configurable disruptions by adjusting KPIs and chart series. Returns a deep copy
suitable for the front-end to render all tabs in "simulated" mode.
"""
import copy
from typing import Any, Dict, List, Optional


def _severity_factor(severity: str, reduce: bool = True) -> float:
    """Multiplier for low/medium/high. For reductions, higher severity = smaller factor."""
    if reduce:
        return {"low": 0.92, "medium": 0.78, "high": 0.55}.get(severity, 0.78)
    return {"low": 1.12, "medium": 1.35, "high": 1.6}.get(severity, 1.35)


def _apply_supplier_delay(
    procurement: Dict[str, Any],
    severity: str,
    scope_vendor: Optional[str],
) -> Dict[str, Any]:
    out = copy.deepcopy(procurement)
    kpis = out.get("kpis") or {}
    f = _severity_factor(severity, reduce=True)
    kpis["total_po_value"] = round((kpis.get("total_po_value") or 0) * f, 0)
    kpis["avg_po_value"] = round((kpis.get("avg_po_value") or 0) * f, 0)
    kpis["total_pos"] = max(1, int((kpis.get("total_pos") or 0) * f))
    kpis["total_po_lines"] = max(1, int((kpis.get("total_po_lines") or 0) * f))
    out["kpis"] = kpis

    vendors = out.get("po_value_by_vendor") or []
    for row in vendors:
        if scope_vendor and row.get("vendor") != scope_vendor:
            continue
        row["value"] = round((row.get("value") or 0) * _severity_factor(severity, reduce=True), 0)
    out["po_value_by_vendor"] = vendors
    return out


def _apply_plant_outage(
    production: Dict[str, Any],
    severity: str,
    scope_plant: Optional[str],
) -> Dict[str, Any]:
    prod_out = copy.deepcopy(production)
    f = _severity_factor(severity, reduce=True)
    pk = prod_out.get("kpis") or {}
    pk["availability_pct"] = round((pk.get("availability_pct") or 0) * f, 1)
    pk["performance_pct"] = round((pk.get("performance_pct") or 0) * f, 1)
    pk["oee_pct"] = round((pk.get("oee_pct") or 0) * f, 1)
    pk["quality_pct"] = round((pk.get("quality_pct") or 100) * (0.95 if severity == "high" else 0.98), 1)
    prod_out["kpis"] = pk

    oee_rows = prod_out.get("oee_by_machine_center") or []
    for row in oee_rows:
        if scope_plant and str(row.get("facility")) != str(scope_plant):
            continue
        row["oee_pct"] = round((row.get("oee_pct") or 0) * f, 1)
        row["availability_pct"] = round((row.get("availability_pct") or 0) * f, 1)
        row["performance_pct"] = round((row.get("performance_pct") or 0) * f, 1)
    prod_out["oee_by_machine_center"] = oee_rows
    return prod_out


def _apply_demand_spike(
    orders: Dict[str, Any],
    severity: str,
    _scope_customer: Optional[str],
) -> Dict[str, Any]:
    out = copy.deepcopy(orders)
    f = _severity_factor(severity, reduce=False)
    kpis = out.get("kpis") or {}
    kpis["total_orders"] = max(1, int((kpis.get("total_orders") or 0) * f))
    kpis["total_order_value"] = round((kpis.get("total_order_value") or 0) * f, 0)
    kpis["avg_order_value"] = round((kpis.get("avg_order_value") or 0) * (f ** 0.5), 0)
    kpis["total_order_qty"] = round((kpis.get("total_order_qty") or 0) * f, 0)
    kpis["unique_customers"] = max(1, int((kpis.get("unique_customers") or 0) * (1 + (f - 1) * 0.5)))
    out["kpis"] = kpis

    status_data = out.get("orders_by_status") or []
    for row in status_data:
        row["count"] = max(0, int((row.get("count") or 0) * f))
    out["orders_by_status"] = status_data
    return out


def run_dashboard_simulation(
    payload: Dict[str, Any],
    disruptions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Apply disruptions to the combined dashboard payload. Modifies a copy and returns it.

    payload must have keys: orders, procurement, production
    (each in the same shape as the dashboard API responses).
    disruptions: list of { "type", "severity", "scope" }.
    Supported types: supplier_delay, plant_outage, demand_spike (logistics_delay and inventory_shortage are no-ops).
    """
    result = copy.deepcopy(payload)
    orders = result.get("orders") or {}
    procurement = result.get("procurement") or {}
    production = result.get("production") or {}

    for d in disruptions:
        dtype = (d.get("type") or "").strip().lower()
        severity = (d.get("severity") or "medium").strip().lower()
        scope = d.get("scope")
        if isinstance(scope, str):
            scope = scope.strip() or None

        if dtype == "supplier_delay":
            result["procurement"] = _apply_supplier_delay(procurement, severity, scope)
            procurement = result["procurement"]
        elif dtype == "plant_outage":
            result["production"] = _apply_plant_outage(production, severity, scope)
            production = result["production"]
        elif dtype == "demand_spike":
            result["orders"] = _apply_demand_spike(orders, severity, scope)
            orders = result["orders"]
        # logistics_delay and inventory_shortage removed (no inventory_delivery tab)

    return result
