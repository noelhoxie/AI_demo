"""
Data layer: SAP and QAD gold tables via Databricks SQL; comments in Postgres.
"""
import logging
from typing import Any

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
            }
    return {
        "total_orders": 1247,
        "total_order_value": 1850000,
        "avg_order_value": 1484,
        "total_order_qty": 382500,
        "total_order_lines": 4100,
        "unique_customers": 42,
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
            }
    return {
        "total_pos": 456,
        "total_po_value": 1245000,
        "avg_po_value": 2730,
        "total_po_qty": 89000,
        "total_po_lines": 2100,
        "unique_suppliers": 28,
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


# --- Inventory & Delivery (SAP gold) ---

def get_inventory_kpis() -> dict[str, Any]:
    """KPIs from sap_gold_kpi_inventory."""
    if databricks_configured() and not USE_MOCK_DATA:
        sql = f"SELECT * FROM `{CATALOG}`.`{SCHEMA}`.sap_gold_kpi_inventory LIMIT 1"
        rows = _run_query(sql)
        if rows:
            r = rows[0]
            return {
                "total_skus": int(r.get("total_skus") or 0),
                "unique_materials": int(r.get("unique_materials") or 0),
                "unique_plants": int(r.get("unique_plants") or 0),
                "total_unrestricted_qty": float(r.get("total_unrestricted_qty") or 0),
                "total_blocked_qty": float(r.get("total_blocked_qty") or 0),
                "total_in_transit_qty": float(r.get("total_in_transit_qty") or 0),
                "total_safety_stock": float(r.get("total_safety_stock") or 0),
                "total_available_qty": float(r.get("total_available_qty") or 0),
            }
    return {
        "total_skus": 320,
        "unique_materials": 180,
        "unique_plants": 4,
        "total_unrestricted_qty": 28500,
        "total_blocked_qty": 1200,
        "total_in_transit_qty": 3100,
        "total_safety_stock": 4500,
        "total_available_qty": 31600,
    }


def get_inventory_charts() -> dict[str, Any]:
    """Inventory by plant from sap_gold_business_inventory."""
    if databricks_configured() and not USE_MOCK_DATA:
        sql = f"""
        SELECT werks AS plant, ROUND(SUM(unrestricted_qty), 0) AS quantity
        FROM `{CATALOG}`.`{SCHEMA}`.sap_gold_business_inventory
        GROUP BY werks ORDER BY quantity DESC
        """
        return {"inventory_by_plant": _run_query(sql)}
    return {
        "inventory_by_plant": [
            {"plant": "1000", "quantity": 12000},
            {"plant": "2000", "quantity": 9800},
            {"plant": "3000", "quantity": 6700},
        ],
    }


def get_delivery_kpis() -> dict[str, Any]:
    """KPIs from sap_gold_kpi_delivery."""
    if databricks_configured() and not USE_MOCK_DATA:
        sql = f"SELECT * FROM `{CATALOG}`.`{SCHEMA}`.sap_gold_kpi_delivery LIMIT 1"
        rows = _run_query(sql)
        if rows:
            r = rows[0]
            return {
                "total_deliveries": int(r.get("total_deliveries") or 0),
                "total_delivery_lines": int(r.get("total_delivery_lines") or 0),
                "total_delivered_qty": float(r.get("total_delivered_qty") or 0),
                "unique_customers": int(r.get("unique_customers") or 0),
                "unique_materials_delivered": int(r.get("unique_materials_delivered") or 0),
            }
    return {
        "total_deliveries": 890,
        "total_delivery_lines": 3200,
        "total_delivered_qty": 245000,
        "unique_customers": 38,
        "unique_materials_delivered": 95,
    }


def get_delivery_charts() -> dict[str, Any]:
    """Deliveries by carrier (tragr) from sap_silver_analyst_delivery."""
    if databricks_configured() and not USE_MOCK_DATA:
        sql = f"""
        SELECT COALESCE(CAST(tragr AS STRING), 'Unknown') AS carrier,
               COUNT(DISTINCT vbeln) AS deliveries,
               ROUND(SUM(lfimg), 0) AS quantity
        FROM `{CATALOG}`.`{SCHEMA}`.sap_silver_analyst_delivery
        GROUP BY tragr ORDER BY deliveries DESC
        """
        return {"deliveries_by_carrier": _run_query(sql)}
    return {
        "deliveries_by_carrier": [
            {"carrier": "01", "deliveries": 320, "quantity": 98000},
            {"carrier": "02", "deliveries": 280, "quantity": 72000},
        ],
    }


# --- Production OEE (QAD gold) ---

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
            return rows[0]
    return {
        "availability_pct": 82.5,
        "performance_pct": 76.2,
        "quality_pct": 98.1,
        "oee_pct": 61.8,
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
