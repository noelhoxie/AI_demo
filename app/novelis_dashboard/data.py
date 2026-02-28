"""
Data layer: query gold tables via Databricks SQL or return mock data.
Used by API routes to serve KPIs and chart data.
"""
import logging
from typing import Any

from config import (
    CATALOG,
    SCHEMA,
    USE_MOCK_DATA,
    databricks_configured,
)

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
    except ImportError:
        log.warning("databricks-sql-connector not available; use mock data.")
        return []
    except Exception as e:
        log.exception("Query failed: %s", e)
        return []


def get_overview_kpis() -> dict[str, Any]:
    """KPIs for Overview tab."""
    if databricks_configured() and not USE_MOCK_DATA:
        # Aggregate from gold / demand / OEE
        orders_sql = f"SELECT COUNT(*) AS total_orders, COALESCE(SUM(kwmeng),0) AS total_quantity FROM `{CATALOG}`.`{SCHEMA}`.demand"
        orders = _run_query(orders_sql)
        oee_sql = f"SELECT ROUND(AVG(oee)*100,1) AS avg_oee_pct FROM `{CATALOG}`.`{SCHEMA}`.qad_gold_oee_by_machine_center"
        oee = _run_query(oee_sql)
        proc_sql = f"SELECT COALESCE(SUM(netwr),0) AS total_po_value FROM `{CATALOG}`.`{SCHEMA}`.procurement"
        proc = _run_query(proc_sql)
        inv_sql = f"SELECT COALESCE(SUM(unrestricted),0) AS total_inventory FROM `{CATALOG}`.`{SCHEMA}`.inventory"
        inv = _run_query(inv_sql)
        return {
            "total_orders": int(orders[0]["total_orders"]) if orders else 0,
            "total_quantity": int(orders[0]["total_quantity"] or 0) if orders else 0,
            "avg_oee_pct": float(oee[0]["avg_oee_pct"] or 0) if oee else 0,
            "total_po_value": float(proc[0]["total_po_value"] or 0) if proc else 0,
            "total_inventory": int(inv[0]["total_inventory"] or 0) if inv else 0,
        }
    return {
        "total_orders": 1247,
        "total_quantity": 382500,
        "avg_oee_pct": 78.4,
        "total_po_value": 1245000,
        "total_inventory": 3280,
    }


def get_supply_chain_data() -> dict[str, Any]:
    """Supply chain KPIs and bar chart data (orders by status, PO value by vendor)."""
    if databricks_configured() and not USE_MOCK_DATA:
        status_sql = f"""
        SELECT status, COUNT(*) AS count FROM `{CATALOG}`.`{SCHEMA}`.demand
        GROUP BY status ORDER BY count DESC
        """
        vendor_sql = f"""
        SELECT vendor_name AS vendor, ROUND(SUM(netwr),0) AS value
        FROM `{CATALOG}`.`{SCHEMA}`.procurement GROUP BY vendor_name ORDER BY value DESC LIMIT 10
        """
        return {
            "orders_by_status": _run_query(status_sql),
            "po_value_by_vendor": _run_query(vendor_sql),
        }
    return {
        "orders_by_status": [
            {"status": "Confirmed", "count": 520},
            {"status": "Open", "count": 380},
            {"status": "Delivered", "count": 347},
        ],
        "po_value_by_vendor": [
            {"vendor": "Alumina Corp", "value": 462500},
            {"vendor": "Bauxite Mining Co", "value": 96000},
            {"vendor": "Metals Alloy Supply", "value": 42000},
            {"vendor": "Carbon Anode Supply", "value": 88000},
            {"vendor": "Refractory Linings Inc", "value": 45000},
        ],
    }


def get_production_oee_data() -> dict[str, Any]:
    """Production OEE from gold table: KPIs and bar chart by machine center."""
    if databricks_configured() and not USE_MOCK_DATA:
        kpi_sql = f"""
        SELECT
          ROUND(AVG(availability)*100,1) AS availability_pct,
          ROUND(AVG(performance)*100,1) AS performance_pct,
          ROUND(AVG(quality)*100,1) AS quality_pct,
          ROUND(AVG(oee)*100,1) AS oee_pct
        FROM `{CATALOG}`.`{SCHEMA}`.qad_gold_oee_by_machine_center
        """
        chart_sql = f"""
        SELECT facility, machine_center,
               ROUND(AVG(oee)*100,1) AS oee_pct,
               ROUND(AVG(availability)*100,1) AS availability_pct,
               ROUND(AVG(performance)*100,1) AS performance_pct,
               ROUND(AVG(quality)*100,1) AS quality_pct
        FROM `{CATALOG}`.`{SCHEMA}`.qad_gold_oee_by_machine_center
        GROUP BY facility, machine_center ORDER BY facility, machine_center
        """
        kpis = _run_query(kpi_sql)
        chart = _run_query(chart_sql)
        return {
            "kpis": kpis[0] if kpis else {},
            "oee_by_machine_center": chart,
        }
    return {
        "kpis": {
            "availability_pct": 82.5,
            "performance_pct": 76.2,
            "quality_pct": 98.1,
            "oee_pct": 61.8,
        },
        "oee_by_machine_center": [
            {"facility": "Oswego", "machine_center": "Hot_Mill_1", "oee_pct": 68.2, "availability_pct": 85, "performance_pct": 78, "quality_pct": 99},
            {"facility": "Oswego", "machine_center": "Caster_1", "oee_pct": 72.1, "availability_pct": 88, "performance_pct": 82, "quality_pct": 99},
            {"facility": "Kennesaw", "machine_center": "Cold_Mill_1", "oee_pct": 58.4, "availability_pct": 79, "performance_pct": 72, "quality_pct": 98},
            {"facility": "Kennesaw", "machine_center": "Coating_Line_1", "oee_pct": 65.0, "availability_pct": 82, "performance_pct": 76, "quality_pct": 99},
            {"facility": "Nachterstedt", "machine_center": "Slitter_1", "oee_pct": 74.5, "availability_pct": 90, "performance_pct": 84, "quality_pct": 98},
        ],
    }


def get_inventory_logistics_data() -> dict[str, Any]:
    """Inventory and logistics: KPIs and bar charts (inventory by plant, deliveries by carrier)."""
    if databricks_configured() and not USE_MOCK_DATA:
        inv_sql = f"""
        SELECT werks AS plant, SUM(unrestricted) AS quantity
        FROM `{CATALOG}`.`{SCHEMA}`.inventory GROUP BY werks ORDER BY quantity DESC
        """
        carrier_sql = f"""
        SELECT carrier, COUNT(*) AS deliveries, SUM(lfimg) AS quantity
        FROM `{CATALOG}`.`{SCHEMA}`.logistics GROUP BY carrier ORDER BY deliveries DESC
        """
        return {
            "inventory_by_plant": _run_query(inv_sql),
            "deliveries_by_carrier": _run_query(carrier_sql),
        }
    return {
        "inventory_by_plant": [
            {"plant": "SMELT-1", "quantity": 1200},
            {"plant": "ROLL-1", "quantity": 1340},
            {"plant": "CAST-1", "quantity": 560},
            {"plant": "EXTR-1", "quantity": 180},
        ],
        "deliveries_by_carrier": [
            {"carrier": "DHL", "deliveries": 45, "quantity": 12000},
            {"carrier": "FedEx", "deliveries": 32, "quantity": 8500},
            {"carrier": "UPS", "deliveries": 28, "quantity": 7200},
            {"carrier": "XPO", "deliveries": 12, "quantity": 2100},
        ],
    }


