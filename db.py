"""
PostgreSQL connection for Supply Chain Control Tower (Databricks OAuth + connection pool).
Extracted from the Dash todo app pattern: env-based connection string and OAuth token refresh.
"""
import os
import time
from typing import Any, Dict, List, Optional

from psycopg import sql
from psycopg_pool import ConnectionPool

# Optional: only needed when running in Databricks with OAuth
try:
    from databricks.sdk import WorkspaceClient
    _HAS_DATABRICKS_SDK = True
except ImportError:
    _HAS_DATABRICKS_SDK = False

workspace_client = None
if _HAS_DATABRICKS_SDK:
    try:
        workspace_client = WorkspaceClient()
    except Exception:
        workspace_client = None

postgres_password: Optional[str] = None
last_password_refresh: float = 0
connection_pool: Optional[ConnectionPool] = None


def _connection_string() -> str:
    """Build connection string from environment (same format as your Dash app)."""
    password = postgres_password or os.getenv("PGPASSWORD", "")
    return (
        f"dbname={os.getenv('PGDATABASE', '')} "
        f"user={os.getenv('PGUSER', '')} "
        f"password={password} "
        f"host={os.getenv('PGHOST', '')} "
        f"port={os.getenv('PGPORT', '5432')} "
        f"sslmode={os.getenv('PGSSLMODE', 'require')} "
        f"application_name={os.getenv('PGAPPNAME', 'supply_chain_tower')}"
    )


def refresh_oauth_token() -> bool:
    """Refresh OAuth token if expired (Databricks). Use PGPASSWORD when not in Databricks."""
    global postgres_password, last_password_refresh
    if workspace_client is not None and (postgres_password is None or time.time() - last_password_refresh > 900):
        try:
            postgres_password = workspace_client.config.oauth_token().access_token
            last_password_refresh = time.time()
        except Exception as e:
            print(f"Failed to refresh OAuth token: {e}")
            return False
    elif postgres_password is None:
        postgres_password = os.getenv("PGPASSWORD")
    return True


def get_connection_pool() -> ConnectionPool:
    """Get or create the connection pool."""
    global connection_pool
    if connection_pool is None:
        refresh_oauth_token()
        connection_pool = ConnectionPool(
            _connection_string(),
            min_size=2,
            max_size=10,
        )
    return connection_pool


def get_connection():
    """Get a connection from the pool. Recreates pool if token expired."""
    global connection_pool
    if workspace_client is not None and (
        postgres_password is None or time.time() - last_password_refresh > 900
    ):
        if connection_pool is not None:
            connection_pool.close()
            connection_pool = None
    return get_connection_pool().connection()


def get_schema_name() -> str:
    """Schema name: {PGAPPNAME}_schema_{PGUSER} (same as your app)."""
    pgappname = os.getenv("PGAPPNAME", "supply_chain_tower").replace("-", "")
    pguser = (os.getenv("PGUSER", "") or "default").replace("-", "")
    return f"{pgappname}_schema_{pguser}"


def init_supply_chain_tables() -> bool:
    """Create schema and supply chain tables (SAP-style)."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                schema = get_schema_name()
                cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))

                cur.execute(sql.SQL("""
                    CREATE TABLE IF NOT EXISTS {}.procurement (
                        id SERIAL PRIMARY KEY,
                        po TEXT NOT NULL,
                        vendor TEXT,
                        vendor_name TEXT,
                        material TEXT,
                        qty INTEGER,
                        value NUMERIC(15,2),
                        status TEXT,
                        delivery DATE,
                        country TEXT
                    )
                """).format(sql.Identifier(schema)))
                try:
                    cur.execute(sql.SQL("ALTER TABLE {}.procurement ADD COLUMN country TEXT").format(sql.Identifier(schema)))
                except Exception:
                    pass  # column may already exist

                cur.execute(sql.SQL("""
                    CREATE TABLE IF NOT EXISTS {}.inventory (
                        id SERIAL PRIMARY KEY,
                        material TEXT,
                        plant TEXT,
                        storage_loc TEXT,
                        unrestricted INTEGER DEFAULT 0,
                        blocked INTEGER DEFAULT 0,
                        in_transit INTEGER DEFAULT 0,
                        reorder_point INTEGER DEFAULT 0
                    )
                """).format(sql.Identifier(schema)))

                cur.execute(sql.SQL("""
                    CREATE TABLE IF NOT EXISTS {}.manufacturing (
                        id SERIAL PRIMARY KEY,
                        order_id TEXT,
                        material TEXT,
                        plant TEXT,
                        qty INTEGER,
                        status TEXT,
                        start_date DATE,
                        end_date DATE
                    )
                """).format(sql.Identifier(schema)))

                cur.execute(sql.SQL("""
                    CREATE TABLE IF NOT EXISTS {}.logistics (
                        id SERIAL PRIMARY KEY,
                        delivery_id TEXT,
                        ship_to TEXT,
                        material TEXT,
                        qty INTEGER,
                        status TEXT,
                        planned_date DATE,
                        carrier TEXT
                    )
                """).format(sql.Identifier(schema)))

                cur.execute(sql.SQL("""
                    CREATE TABLE IF NOT EXISTS {}.demand (
                        id SERIAL PRIMARY KEY,
                        order_id TEXT,
                        customer TEXT,
                        material TEXT,
                        qty INTEGER,
                        request_date DATE,
                        status TEXT,
                        forecast_qty INTEGER
                    )
                """).format(sql.Identifier(schema)))

                conn.commit()
        return True
    except Exception as e:
        print(f"Database initialization error: {e}")
        return False


def _row_to_sap_procurement(row: tuple) -> Dict[str, Any]:
    # id, po, vendor, vendor_name, material, qty, value, status, delivery [, country]
    return {
        "po": row[1],
        "vendor": row[2] or "",
        "vendorName": row[3] or row[2] or "",
        "material": row[4] or "",
        "qty": row[5] or 0,
        "value": float(row[6] or 0),
        "status": row[7] or "Open",
        "delivery": row[8].strftime("%Y-%m-%d") if hasattr(row[8], "strftime") else str(row[8] or ""),
        "country": row[9] if len(row) > 9 else "",
    }


def _row_to_sap_inventory(row: tuple) -> Dict[str, Any]:
    return {
        "material": row[1],
        "plant": row[2],
        "storageLoc": row[3],
        "unrestricted": row[4] or 0,
        "blocked": row[5] or 0,
        "inTransit": row[6] or 0,
        "reorderPoint": row[7] or 0,
    }


def _row_to_sap_manufacturing(row: tuple) -> Dict[str, Any]:
    return {
        "order": row[1],
        "material": row[2],
        "plant": row[3],
        "qty": row[4] or 0,
        "status": row[5] or "Released",
        "start": row[6].strftime("%Y-%m-%d") if row[6] and hasattr(row[6], "strftime") else str(row[6] or ""),
        "end": row[7].strftime("%Y-%m-%d") if row[7] and hasattr(row[7], "strftime") else str(row[7] or ""),
    }


def _row_to_sap_logistics(row: tuple) -> Dict[str, Any]:
    return {
        "delivery": row[1],
        "shipTo": row[2],
        "material": row[3],
        "qty": row[4] or 0,
        "status": row[5] or "Pending",
        "planned": row[6].strftime("%Y-%m-%d") if row[6] and hasattr(row[6], "strftime") else str(row[6] or ""),
        "carrier": row[7] or "",
    }


def _row_to_sap_demand(row: tuple) -> Dict[str, Any]:
    return {
        "order": row[1],
        "customer": row[2],
        "material": row[3],
        "qty": row[4] or 0,
        "requestDate": row[5].strftime("%Y-%m-%d") if row[5] and hasattr(row[5], "strftime") else str(row[5] or ""),
        "status": row[6] or "Open",
        "forecastQty": row[7] or 0,
    }


def get_procurement() -> List[Dict[str, Any]]:
    """Fetch procurement rows in control tower SAP format."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                schema = get_schema_name()
                cur.execute(sql.SQL("""
                    SELECT id, po, vendor, vendor_name, material, qty, value, status, delivery, country
                    FROM {}.procurement ORDER BY delivery DESC
                """).format(sql.Identifier(schema)))
                return [_row_to_sap_procurement(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"get_procurement error: {e}")
        return []


def get_inventory() -> List[Dict[str, Any]]:
    """Fetch inventory rows in control tower SAP format."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                schema = get_schema_name()
                cur.execute(sql.SQL("""
                    SELECT id, material, plant, storage_loc, unrestricted, blocked, in_transit, reorder_point
                    FROM {}.inventory ORDER BY material, plant
                """).format(sql.Identifier(schema)))
                return [_row_to_sap_inventory(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"get_inventory error: {e}")
        return []


def get_manufacturing() -> List[Dict[str, Any]]:
    """Fetch manufacturing rows in control tower SAP format."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                schema = get_schema_name()
                cur.execute(sql.SQL("""
                    SELECT id, order_id, material, plant, qty, status, start_date, end_date
                    FROM {}.manufacturing ORDER BY start_date DESC
                """).format(sql.Identifier(schema)))
                return [_row_to_sap_manufacturing(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"get_manufacturing error: {e}")
        return []


def get_logistics() -> List[Dict[str, Any]]:
    """Fetch logistics rows in control tower SAP format."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                schema = get_schema_name()
                cur.execute(sql.SQL("""
                    SELECT id, delivery_id, ship_to, material, qty, status, planned_date, carrier
                    FROM {}.logistics ORDER BY planned_date DESC
                """).format(sql.Identifier(schema)))
                return [_row_to_sap_logistics(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"get_logistics error: {e}")
        return []


def get_demand() -> List[Dict[str, Any]]:
    """Fetch demand rows in control tower SAP format."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                schema = get_schema_name()
                cur.execute(sql.SQL("""
                    SELECT id, order_id, customer, material, qty, request_date, status, forecast_qty
                    FROM {}.demand ORDER BY request_date DESC
                """).format(sql.Identifier(schema)))
                return [_row_to_sap_demand(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"get_demand error: {e}")
        return []


def get_sap_data() -> Dict[str, List[Dict[str, Any]]]:
    """Return full SAP-style payload for the control tower (window.loadSAPData)."""
    return {
        "procurement": get_procurement(),
        "inventory": get_inventory(),
        "manufacturing": get_manufacturing(),
        "logistics": get_logistics(),
        "demand": get_demand(),
    }


def seed_sap_data(sap_dict: Dict[str, List[Dict[str, Any]]]) -> bool:
    """Insert SAP-style data (e.g. from build_sap_data) into the supply chain tables."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                schema = get_schema_name()
                for r in sap_dict.get("procurement", []):
                    cur.execute(
                        sql.SQL("""
                            INSERT INTO {}.procurement (po, vendor, vendor_name, material, qty, value, status, delivery, country)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::date, %s)
                        """).format(sql.Identifier(schema)),
                        (
                            r.get("po"), r.get("vendor"), r.get("vendorName"),
                            r.get("material"), r.get("qty"), r.get("value"),
                            r.get("status"), r.get("delivery"), r.get("country") or None,
                        ),
                    )
                for r in sap_dict.get("inventory", []):
                    cur.execute(
                        sql.SQL("""
                            INSERT INTO {}.inventory (material, plant, storage_loc, unrestricted, blocked, in_transit, reorder_point)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """).format(sql.Identifier(schema)),
                        (
                            r.get("material"), r.get("plant"), r.get("storageLoc"),
                            r.get("unrestricted"), r.get("blocked"), r.get("inTransit"), r.get("reorderPoint"),
                        ),
                    )
                for r in sap_dict.get("manufacturing", []):
                    cur.execute(
                        sql.SQL("""
                            INSERT INTO {}.manufacturing (order_id, material, plant, qty, status, start_date, end_date)
                            VALUES (%s, %s, %s, %s, %s, %s::date, %s::date)
                        """).format(sql.Identifier(schema)),
                        (
                            r.get("order"), r.get("material"), r.get("plant"), r.get("qty"),
                            r.get("status"), r.get("start"), r.get("end"),
                        ),
                    )
                for r in sap_dict.get("logistics", []):
                    cur.execute(
                        sql.SQL("""
                            INSERT INTO {}.logistics (delivery_id, ship_to, material, qty, status, planned_date, carrier)
                            VALUES (%s, %s, %s, %s, %s, %s::date, %s)
                        """).format(sql.Identifier(schema)),
                        (
                            r.get("delivery"), r.get("shipTo"), r.get("material"), r.get("qty"),
                            r.get("status"), r.get("planned"), r.get("carrier"),
                        ),
                    )
                for r in sap_dict.get("demand", []):
                    cur.execute(
                        sql.SQL("""
                            INSERT INTO {}.demand (order_id, customer, material, qty, request_date, status, forecast_qty)
                            VALUES (%s, %s, %s, %s, %s::date, %s, %s)
                        """).format(sql.Identifier(schema)),
                        (
                            r.get("order"), r.get("customer"), r.get("material"), r.get("qty"),
                            r.get("requestDate"), r.get("status"), r.get("forecastQty"),
                        ),
                    )
                conn.commit()
        return True
    except Exception as e:
        print(f"seed_sap_data error: {e}")
        return False


def seed_procurement_only(procurement_list: List[Dict[str, Any]]) -> bool:
    """Replace all procurement rows with the given list (e.g. 1000 POs from build_sap_data)."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                schema = get_schema_name()
                cur.execute(sql.SQL("DELETE FROM {}.procurement").format(sql.Identifier(schema)))
                for r in procurement_list:
                    cur.execute(
                        sql.SQL("""
                            INSERT INTO {}.procurement (po, vendor, vendor_name, material, qty, value, status, delivery, country)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::date, %s)
                        """).format(sql.Identifier(schema)),
                        (
                            r.get("po"), r.get("vendor"), r.get("vendorName"),
                            r.get("material"), r.get("qty"), r.get("value"),
                            r.get("status"), r.get("delivery"), r.get("country") or None,
                        ),
                    )
                conn.commit()
        return True
    except Exception as e:
        print(f"seed_procurement_only error: {e}")
        return False
