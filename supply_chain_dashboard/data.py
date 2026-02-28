"""
Data layer: SAP and QAD gold tables via Databricks SQL; comments in Postgres.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from config import CATALOG, SCHEMA, USE_MOCK_DATA, databricks_configured

log = logging.getLogger(__name__)


def _run_query(sql: str) -> list[dict[str, Any]]:
    """Execute SQL on Databricks warehouse; return list of dicts."""
    if not databricks_configured() or USE_MOCK_DATA:
        return []
    import os
    host = (os.environ.get("DATABRICKS_HOST", "") or "").replace("https://", "").split("/")[0]
    token = os.environ.get("DATABRICKS_TOKEN", "")
    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
    if not all([host, token, warehouse_id]):
        return []
    try:
        from databricks import sql as dbsql
        conn = dbsql.connect(
            server_hostname=host,
            http_path=f"/sql/1.0/warehouses/{warehouse_id}",
            access_token=token,
        )
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        log.exception("Query failed: %s", e)
        return []


# --- Orders (SAP gold) ---

def get_orders_kpis() -> dict[str, Any]:
    """KPIs from sap_gold_kpi_orders."""
    if databricks_configured() and not USE_MOCK_DATA:
        sql = f"SELECT * FROM `{CATALOG}`.`{SCHEMA}`.sap_gold_kpi_orders LIMIT 1"
        rows = _run_query(sql)
        if rows:
            r = rows[0]
            return {
                "total_orders": int(r.get("total_orders") or 0),
                "total_order_value": float(r.get("total_order_value") or 0),
                "avg_order_value": float(r.get("avg_order_value") or 0),
                "total_order_qty": float(r.get("total_order_qty") or 0),
                "total_order_lines": int(r.get("total_order_lines") or 0),
                "unique_customers": int(r.get("unique_customers") or 0),
                "total_orders_target": 1500,
                "total_order_value_target": 2000000,
                "avg_order_value_target": 1500,
                "total_order_qty_target": 400000,
                "unique_customers_target": 50,
            }
    return {
        "total_orders": 1247,
        "total_order_value": 1850000,
        "avg_order_value": 1484,
        "total_order_qty": 382500,
        "total_order_lines": 4100,
        "unique_customers": 42,
        "total_orders_target": 1500,
        "total_order_value_target": 2000000,
        "avg_order_value_target": 1500,
        "total_order_qty_target": 400000,
        "unique_customers_target": 50,
    }


def get_orders_charts() -> dict[str, Any]:
    """Orders by rejection status from sap_gold_business_orders."""
    if databricks_configured() and not USE_MOCK_DATA:
        sql = f"""
        SELECT COALESCE(absta, 'Unknown') AS status, COUNT(*) AS count
        FROM `{CATALOG}`.`{SCHEMA}`.sap_gold_business_orders
        GROUP BY absta ORDER BY count DESC
        """
        return {"orders_by_status": _run_query(sql)}
    return {
        "orders_by_status": [
            {"status": "A", "count": 820},
            {"status": "B", "count": 310},
            {"status": "C", "count": 117},
        ],
    }


# --- Procurement (SAP gold) ---

def get_procurement_kpis() -> dict[str, Any]:
    """KPIs from sap_gold_kpi_procurement."""
    if databricks_configured() and not USE_MOCK_DATA:
        sql = f"SELECT * FROM `{CATALOG}`.`{SCHEMA}`.sap_gold_kpi_procurement LIMIT 1"
        rows = _run_query(sql)
        if rows:
            r = rows[0]
            return {
                "total_pos": int(r.get("total_pos") or 0),
                "total_po_value": float(r.get("total_po_value") or 0),
                "avg_po_value": float(r.get("avg_po_value") or 0),
                "total_po_qty": float(r.get("total_po_qty") or 0),
                "total_po_lines": int(r.get("total_po_lines") or 0),
                "unique_suppliers": int(r.get("unique_suppliers") or 0),
                "total_pos_target": 500,
                "total_po_value_target": 1500000,
                "avg_po_value_target": 3000,
                "unique_suppliers_target": 30,
            }
    return {
        "total_pos": 456,
        "total_po_value": 1245000,
        "avg_po_value": 2730,
        "total_po_qty": 89000,
        "total_po_lines": 2100,
        "unique_suppliers": 28,
        "total_pos_target": 500,
        "total_po_value_target": 1500000,
        "avg_po_value_target": 3000,
        "unique_suppliers_target": 30,
    }


def get_procurement_charts() -> dict[str, Any]:
    """PO value by vendor (lifnr) from sap_gold_business_procurement."""
    if databricks_configured() and not USE_MOCK_DATA:
        sql = f"""
        SELECT lifnr AS vendor, ROUND(SUM(total_value), 0) AS value
        FROM `{CATALOG}`.`{SCHEMA}`.sap_gold_business_procurement
        GROUP BY lifnr ORDER BY value DESC LIMIT 10
        """
        return {"po_value_by_vendor": _run_query(sql)}
    return {
        "po_value_by_vendor": [
            {"vendor": "V001", "value": 462500},
            {"vendor": "V002", "value": 260000},
            {"vendor": "V003", "value": 180000},
        ],
    }


def get_supplier_scorecard() -> list[dict[str, Any]]:
    """Supplier scorecard list: vendor_id, vendor_name, score (0-100), tier, on_time_pct, quality_pct, avg_lead_time_days, total_spend, po_count."""
    if databricks_configured() and not USE_MOCK_DATA:
        # If you have a gold scorecard table, query it; otherwise derive from procurement
        sql = f"""
        SELECT lifnr AS vendor_id, lifnr AS vendor_name,
               ROUND(SUM(total_value), 0) AS total_spend,
               COUNT(*) AS po_count
        FROM `{CATALOG}`.`{SCHEMA}`.sap_gold_business_procurement
        GROUP BY lifnr ORDER BY total_spend DESC LIMIT 50
        """
        rows = _run_query(sql) or []
        out = []
        for i, r in enumerate(rows):
            vid = (r.get("vendor_id") or r.get("vendor_name") or "").strip()
            spend = float(r.get("total_spend") or 0)
            count = int(r.get("po_count") or 0)
            # Placeholder scores when no scorecard table exists
            score = min(98, 72 + (i % 25))
            tier = "A" if score >= 85 else "B" if score >= 70 else "C"
            out.append({
                "vendor_id": vid,
                "vendor_name": vid,
                "score": score,
                "tier": tier,
                "on_time_delivery_pct": min(99, 75 + (i % 22)),
                "quality_acceptance_pct": min(100, 88 + (i % 11)),
                "avg_lead_time_days": 7 + (i % 14),
                "total_spend": spend,
                "po_count": count,
            })
        return out
    # Mock scorecard
    return [
        {"vendor_id": "V001", "vendor_name": "Acme Materials Co", "score": 92, "tier": "A", "on_time_delivery_pct": 96, "quality_acceptance_pct": 98, "avg_lead_time_days": 8, "total_spend": 462500, "po_count": 42},
        {"vendor_id": "V002", "vendor_name": "Beta Components Inc", "score": 78, "tier": "B", "on_time_delivery_pct": 82, "quality_acceptance_pct": 91, "avg_lead_time_days": 12, "total_spend": 260000, "po_count": 28},
        {"vendor_id": "V003", "vendor_name": "Gamma Supply Ltd", "score": 65, "tier": "C", "on_time_delivery_pct": 71, "quality_acceptance_pct": 88, "avg_lead_time_days": 18, "total_spend": 180000, "po_count": 19},
        {"vendor_id": "V004", "vendor_name": "Delta Logistics", "score": 88, "tier": "A", "on_time_delivery_pct": 94, "quality_acceptance_pct": 96, "avg_lead_time_days": 6, "total_spend": 145000, "po_count": 31},
        {"vendor_id": "V005", "vendor_name": "Epsilon Parts", "score": 73, "tier": "B", "on_time_delivery_pct": 79, "quality_acceptance_pct": 89, "avg_lead_time_days": 14, "total_spend": 98000, "po_count": 15},
    ]


def get_supplier_scorecard_detail(vendor_id: str) -> Optional[dict[str, Any]]:
    """Full scorecard and metrics for one supplier (for detail view / PDF)."""
    vendor_id = (vendor_id or "").strip()
    if not vendor_id:
        return None
    list_data = get_supplier_scorecard()
    for s in list_data:
        if (s.get("vendor_id") or s.get("vendor_name") or "").strip() == vendor_id:
            # Add extra detail fields for the report
            detail = dict(s)
            detail["invoices_paid_on_time_pct"] = min(99, (detail.get("score", 0) + 2) % 100)
            detail["dispute_count_12m"] = 0 if detail.get("tier") == "A" else (1 if detail.get("tier") == "B" else 2)
            detail["last_audit_date"] = (datetime.now().date() - timedelta(days=30 + hash(vendor_id) % 60)).strftime("%Y-%m-%d")
            detail["contract_expiry"] = (datetime.now().date() + timedelta(days=180 + hash(vendor_id) % 365)).strftime("%Y-%m-%d")
            return detail
    return None


# In-memory store for newly created POs (shown on Outstanding POs and merged into counts)
_new_purchase_orders: list[dict[str, Any]] = []
_new_po_counter = 0
# Overrides for POs from gold/mock (keyed by po_number) so edits persist in session
_po_overrides: dict[str, dict[str, Any]] = {}


def update_purchase_order(
    po_number: str,
    vendor: Optional[str] = None,
    value: Optional[float] = None,
    order_date: Optional[str] = None,
    delivery_date: Optional[str] = None,
    status: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Update a purchase order. For NEW-* POs updates in-place; for others stores overrides. Returns updated PO or None if not found."""
    po_number = (po_number or "").strip()
    if not po_number:
        return None
    if po_number.startswith("NEW-"):
        for po in _new_purchase_orders:
            if po.get("po_number") == po_number:
                if vendor is not None:
                    po["vendor"] = vendor.strip()
                if value is not None:
                    po["value"] = round(value, 2)
                if order_date is not None:
                    po["order_date"] = order_date.strip() or None
                if delivery_date is not None:
                    po["delivery_date"] = delivery_date.strip() or None
                if status is not None:
                    po["status"] = status.strip() or "Open"
                return {k: v for k, v in po.items() if k in ("po_number", "vendor", "value", "order_date", "status")}
        return None
    # Non-NEW: store overrides
    if po_number not in _po_overrides:
        _po_overrides[po_number] = {}
    o = _po_overrides[po_number]
    if vendor is not None:
        o["vendor"] = vendor.strip()
    if value is not None:
        o["value"] = round(value, 2)
    if order_date is not None:
        o["order_date"] = order_date.strip() or None
    if status is not None:
        o["status"] = status.strip() or "Open"
    return None  # caller can re-fetch list


def add_purchase_order(
    vendor: str,
    order_date: str,
    value: float,
    delivery_date: Optional[str] = None,
    line_items: Optional[list[dict[str, Any]]] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    """Append a new PO to the in-memory store. Returns the created PO (with po_number, status)."""
    global _new_po_counter
    _new_po_counter += 1
    po_number = "NEW-" + str(_new_po_counter)
    po = {
        "po_number": po_number,
        "vendor": (vendor or "").strip(),
        "value": round(value, 2),
        "order_date": (order_date or "").strip() or None,
        "delivery_date": (delivery_date or "").strip() or None,
        "status": "Open",
        "line_items": line_items or [],
        "notes": (notes or "").strip() or None,
    }
    _new_purchase_orders.append(po)
    return {k: v for k, v in po.items() if k in ("po_number", "vendor", "value", "order_date", "status")}


def get_outstanding_pos() -> list[dict[str, Any]]:
    """List of outstanding purchase orders (PO number, vendor, value, order_date, status). New POs first."""
    if databricks_configured() and not USE_MOCK_DATA:
        sql = f"""
        SELECT lifnr AS vendor, ROUND(SUM(total_value), 0) AS value
        FROM `{CATALOG}`.`{SCHEMA}`.sap_gold_business_procurement
        GROUP BY lifnr ORDER BY value DESC LIMIT 500
        """
        rows = _run_query(sql) or []
        out = [
            {"po_number": "PO-" + str((r.get("vendor") or "").strip()), "vendor": r.get("vendor"), "value": r.get("value"), "order_date": None, "status": "Open"}
            for r in rows
        ]
    else:
        vendors = ["V001", "V002", "V003", "V004", "V005"]
        statuses = ["Open", "Open", "Open", "Partial", "Sent", "Pending"]
        base_date = datetime(2025, 1, 1)
        out = []
        for i in range(1, 101):
            vendor = vendors[(i - 1) % len(vendors)]
            status = statuses[(i - 1) % len(statuses)]
            order_date = (base_date + timedelta(days=(i * 3) % 90)).strftime("%Y-%m-%d")
            value = 15000 + (i * 1200) % 180000
            out.append({
                "po_number": "45000" + str(12340 + i),
                "vendor": vendor,
                "value": value,
                "order_date": order_date,
                "status": status,
            })
    # Apply overrides to existing rows
    for i, row in enumerate(out):
        over = _po_overrides.get(row.get("po_number"))
        if over:
            row = dict(row)
            row.update({k: v for k, v in over.items() if v is not None})
            out[i] = row
    # Prepend newly created POs so they appear at top
    for po in reversed(_new_purchase_orders):
        out.insert(0, {
            "po_number": po.get("po_number"),
            "vendor": po.get("vendor"),
            "value": po.get("value"),
            "order_date": po.get("order_date"),
            "status": po.get("status", "Open"),
        })
    return out


# --- Production (QAD gold) ---

def get_production_kpis() -> dict[str, Any]:
    """OEE KPIs from qad_gold_oee_by_machine_center."""
    if databricks_configured() and not USE_MOCK_DATA:
        sql = f"""
        SELECT
          ROUND(AVG(availability) * 100, 1) AS availability_pct,
          ROUND(AVG(performance) * 100, 1) AS performance_pct,
          ROUND(AVG(quality) * 100, 1) AS quality_pct,
          ROUND(AVG(oee) * 100, 1) AS oee_pct
        FROM `{CATALOG}`.`{SCHEMA}`.qad_gold_oee_by_machine_center
        """
        rows = _run_query(sql)
        if rows:
            r = dict(rows[0])
            r.setdefault("availability_pct_target", 85)
            r.setdefault("performance_pct_target", 80)
            r.setdefault("quality_pct_target", 99)
            r.setdefault("oee_pct_target", 65)
            return r
    return {
        "availability_pct": 82.5,
        "performance_pct": 76.2,
        "quality_pct": 98.1,
        "oee_pct": 61.8,
        "availability_pct_target": 85,
        "performance_pct_target": 80,
        "quality_pct_target": 99,
        "oee_pct_target": 65,
    }


def get_production_charts() -> dict[str, Any]:
    """OEE by machine center from qad_gold_oee_by_machine_center."""
    if databricks_configured() and not USE_MOCK_DATA:
        sql = f"""
        SELECT facility, machine_center,
               ROUND(AVG(oee) * 100, 1) AS oee_pct,
               ROUND(AVG(availability) * 100, 1) AS availability_pct,
               ROUND(AVG(performance) * 100, 1) AS performance_pct,
               ROUND(AVG(quality) * 100, 1) AS quality_pct
        FROM `{CATALOG}`.`{SCHEMA}`.qad_gold_oee_by_machine_center
        GROUP BY facility, machine_center ORDER BY facility, machine_center
        """
        return {"oee_by_machine_center": _run_query(sql)}
    return {
        "oee_by_machine_center": [
            {"facility": "Oswego", "machine_center": "Hot_Mill_1", "oee_pct": 68.2},
            {"facility": "Kennesaw", "machine_center": "Cold_Mill_1", "oee_pct": 58.4},
            {"facility": "Nachterstedt", "machine_center": "Slitter_1", "oee_pct": 74.5},
        ],
    }


def get_production_oee_forecast_7d() -> dict[str, Any]:
    """Forecasted OEE by line for the next 7 days. Returns labels (day names) and series (one per line with 7 values)."""
    charts = get_production_charts()
    rows = charts.get("oee_by_machine_center") or []
    if not rows:
        return {"labels": [], "series": []}

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    labels = [(today + timedelta(days=i)).strftime("%a %m/%d") for i in range(7)]
    # Use a simple deterministic "forecast": base OEE + small daily drift so chart is readable
    series = []
    for r in rows:
        line_name = f"{r.get('facility', '')} — {r.get('machine_center', '')}".strip(" — ")
        base = float(r.get("oee_pct") or 0)
        # Slight trend and variation per day (deterministic from line name)
        seed = hash(line_name) % 100
        values = []
        for i in range(7):
            drift = ((seed + i * 3) % 11) - 5  # -5 to +5
            v = max(0, min(100, round(base + drift * 0.8, 1)))
            values.append(v)
        series.append({"line": line_name, "data": values})
    return {"labels": labels, "series": series}


# Mutable list for production orders so edits persist (used when not querying Databricks)
_production_orders_cache: Optional[list[dict[str, Any]]] = None


def get_production_orders() -> list[dict[str, Any]]:
    """Production orders for the Production orders tab. From gold table when available; otherwise mock (editable in memory)."""
    global _production_orders_cache
    if databricks_configured() and not USE_MOCK_DATA:
        # Optional: query production orders gold table when available
        # sql = f"SELECT order_id, material, plant, quantity, status, start_date, end_date FROM ..."
        pass
    if _production_orders_cache is not None:
        return _production_orders_cache
    base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    _production_orders_cache = [
        {"order_id": "1000001", "material": "FG-9001", "plant": "1000", "quantity": 1000, "status": "Released", "start_date": (base - timedelta(days=4)).strftime("%Y-%m-%d"), "end_date": (base + timedelta(days=2)).strftime("%Y-%m-%d")},
        {"order_id": "1000002", "material": "FG-9002", "plant": "1000", "quantity": 500, "status": "Confirmed", "start_date": (base - timedelta(days=2)).strftime("%Y-%m-%d"), "end_date": (base + timedelta(days=5)).strftime("%Y-%m-%d")},
        {"order_id": "1000003", "material": "FG-9001", "plant": "2000", "quantity": 750, "status": "Completed", "start_date": (base - timedelta(days=12)).strftime("%Y-%m-%d"), "end_date": (base - timedelta(days=7)).strftime("%Y-%m-%d")},
        {"order_id": "1000004", "material": "FG-9003", "plant": "1000", "quantity": 2000, "status": "Released", "start_date": (base - timedelta(days=1)).strftime("%Y-%m-%d"), "end_date": (base + timedelta(days=8)).strftime("%Y-%m-%d")},
        {"order_id": "1000005", "material": "FG-9002", "plant": "2000", "quantity": 1200, "status": "Confirmed", "start_date": base.strftime("%Y-%m-%d"), "end_date": (base + timedelta(days=6)).strftime("%Y-%m-%d")},
        {"order_id": "1000006", "material": "FG-9001", "plant": "1000", "quantity": 800, "status": "Completed", "start_date": (base - timedelta(days=10)).strftime("%Y-%m-%d"), "end_date": (base - timedelta(days=5)).strftime("%Y-%m-%d")},
    ]
    return _production_orders_cache


def update_production_order(
    order_id: str,
    material: Optional[str] = None,
    plant: Optional[str] = None,
    quantity: Optional[int] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Update a production order in the in-memory list. Returns updated order or None."""
    order_id = (order_id or "").strip()
    if not order_id:
        return None
    orders = get_production_orders()
    for o in orders:
        if (o.get("order_id") or "") == order_id:
            if material is not None:
                o["material"] = material.strip()
            if plant is not None:
                o["plant"] = plant.strip()
            if quantity is not None:
                o["quantity"] = int(quantity)
            if status is not None:
                o["status"] = status.strip()
            if start_date is not None:
                o["start_date"] = start_date.strip() or ""
            if end_date is not None:
                o["end_date"] = end_date.strip() or ""
            return dict(o)
    return None


# --- Inventory optimization ---

def get_inventory_optimization_kpis() -> dict[str, Any]:
    """KPIs for inventory optimization (turnover, days of supply, service level)."""
    if databricks_configured() and not USE_MOCK_DATA:
        # Placeholder: could query inventory gold tables when available
        pass
    return {
        "inventory_turnover": 5.2,
        "days_of_supply": 42,
        "service_level_pct": 96.8,
        "stockout_events_30d": 3,
        "safety_stock_coverage_days": 14,
        "supplier_fill_rate_pct": 94.2,
        "open_inbound_orders": 127,
        "inventory_value_total": 4000000,
        "inventory_turnover_target": 6,
        "days_of_supply_target": 45,
        "service_level_pct_target": 98,
        "inventory_value_total_target": 3500000,
        "supplier_fill_rate_pct_target": 96,
        "open_inbound_orders_target": 150,
    }


def get_inventory_optimization_charts() -> dict[str, Any]:
    """Charts for inventory optimization: inventory by location, by ABC class."""
    if databricks_configured() and not USE_MOCK_DATA:
        pass
    return {
        "inventory_by_location": [
            {"location": "Oswego", "value": 1240000, "units": 42000},
            {"location": "Kennesaw", "value": 980000, "units": 31500},
            {"location": "Nachterstedt", "value": 760000, "units": 26800},
            {"location": "South Central DC", "value": 540000, "units": 18200},
            {"location": "West Coast DC", "value": 480000, "units": 16100},
        ],
        "inventory_by_abc_class": [
            {"class": "A", "value_pct": 72, "sku_count": 45},
            {"class": "B", "value_pct": 22, "sku_count": 180},
            {"class": "C", "value_pct": 6, "sku_count": 520},
        ],
    }
