import os

# Databricks connection (bronze layer reads — machine data)
DATABRICKS_HOST      = os.environ.get("DATABRICKS_HOST", "")
DATABRICKS_TOKEN     = os.environ.get("DATABRICKS_TOKEN", "")
DATABRICKS_WAREHOUSE = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
DATABRICKS_CATALOG   = os.environ.get("DATABRICKS_CATALOG", "nah_demo")
DATABRICKS_SCHEMA    = os.environ.get("DATABRICKS_SCHEMA", "airtech_lab_bronze")

# PostgreSQL — Supabase (or any standard PostgreSQL provider)
# Set DATABASE_URL to your Supabase connection string:
#   postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
# LAB_DB_URL is kept as a legacy alias.
DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("LAB_DB_URL")
    or ""
)

# Lab machines in the bronze layer
LAB_MACHINES = [
    {
        "id": "machine_pressure",
        "name": "Pressure/Leak Tester — Station A",
        "table": f"{DATABRICKS_CATALOG}.{DATABRICKS_SCHEMA}.machine_pressure_readings",
        "type": "pressure",
        "location": "Bay 1",
    },
    {
        "id": "machine_flow",
        "name": "Flow/Performance Tester — Station B",
        "table": f"{DATABRICKS_CATALOG}.{DATABRICKS_SCHEMA}.machine_flow_readings",
        "type": "flow",
        "location": "Bay 2",
    },
]

# Refresh machines list after env is set (catalog/schema may change)
def get_machines():
    catalog = DATABRICKS_CATALOG
    schema  = DATABRICKS_SCHEMA
    return [
        {
            "id": "machine_pressure",
            "name": "Pressure/Leak Tester — Station A",
            "table": f"{catalog}.{schema}.machine_pressure_readings",
            "type": "pressure",
            "location": "Bay 1",
        },
        {
            "id": "machine_flow",
            "name": "Flow/Performance Tester — Station B",
            "table": f"{catalog}.{schema}.machine_flow_readings",
            "type": "flow",
            "location": "Bay 2",
        },
    ]
