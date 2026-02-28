# Data pipeline

All data pipelines for the Supply Chain Control Tower. Used by the Databricks bundle jobs and by local scripts.

## Structure

| Path | Description |
|------|-------------|
| **sap/** | SAP bronze → silver → gold (procurement, orders, delivery, inventory, KPIs). Notebooks run as Databricks job tasks. |
| **qad/** | QAD manufacturing pipeline (bronze, silver, gold OEE). See [qad/README.md](qad/README.md). |
| **cleanup_schema.py** | Drops and recreates schema tables (used by repopulate job). |
| **01_setup_sap_delta_tables.py**, **02_control_tower_dashboard.py**, **03_demand_forecast.py** | Setup and demo notebooks. |
| **build_sap_data.py** | Builds mock SAP-style data (used by control tower Flask app and seeding). |
| **seed_1000_pos.py** | Seeds purchase orders for testing. |

## Running pipelines

Deploy and run jobs via the Databricks bundle (from repo root):

```bash
databricks bundle deploy -t dev
# Then run jobs from the workspace: SAP_bronze_ingest, repopulate_ai_sc_test, qad_bronze_ingest, etc.
```

Or run a single job:

```bash
databricks bundle run -t dev SAP_bronze_ingest
```

Catalog and schema are set in `databricks.yml` variables (`catalog`, `schema`).
