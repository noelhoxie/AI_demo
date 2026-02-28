"""Configuration for Novelis Supply Chain & Production Dashboard."""
import os
from dotenv import load_dotenv

load_dotenv()

# Databricks SQL
DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST", "").rstrip("/")
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN", "")
DATABRICKS_WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")

# Unity Catalog (gold tables live here)
CATALOG = os.environ.get("CATALOG", "serverless_hadnqm_catalog")
SCHEMA = os.environ.get("SCHEMA", "ai_sc_test")

# Use mock data when Databricks is not configured (e.g. local dev)
USE_MOCK_DATA = os.environ.get("USE_MOCK_DATA", "").strip().lower() in ("1", "true", "yes")


def databricks_configured():
    return bool(DATABRICKS_HOST and DATABRICKS_TOKEN and DATABRICKS_WAREHOUSE_ID)
