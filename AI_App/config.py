"""Configuration for Supply Chain Dashboard (SAP + QAD gold, Postgres comments)."""
import os
from dotenv import load_dotenv

load_dotenv()

# Databricks SQL (gold tables)
DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST", "").rstrip("/")
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN", "")
DATABRICKS_WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")

# Unity Catalog
CATALOG = os.environ.get("CATALOG", "serverless_hadnqm_catalog")
SCHEMA = os.environ.get("SCHEMA", "ai_sc_test")

# Postgres (comments) — same env as db_connection: PGHOST, PGDATABASE, PGUSER, PGPASSWORD, PGPORT, PGSSLMODE, PGAPPNAME
USE_MOCK_DATA = os.environ.get("USE_MOCK_DATA", "").strip().lower() in ("1", "true", "yes")


def databricks_configured():
    return bool(DATABRICKS_HOST and DATABRICKS_TOKEN and DATABRICKS_WAREHOUSE_ID)


def postgres_configured():
    return bool(os.environ.get("PGHOST") and os.environ.get("PGDATABASE") and os.environ.get("PGUSER"))
