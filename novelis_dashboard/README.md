# Novelis-Style Supply Chain & Production Dashboard

Production-ready Flask app with **4 tabs**: Overview, Supply Chain, Production OEE, and Inventory & Logistics. KPIs at the top and bar charts underneath, themed to match **Novelis** branding (navy blue, light gray, clean typography). Data is read from Unity Catalog **gold tables** (and related bronze/silver where needed).

## Features

- **Overview** — Total orders, total quantity, average OEE %, PO value, total inventory; bar charts for orders by status and PO value by vendor.
- **Supply Chain** — Orders by status and PO value by vendor (bar charts).
- **Production OEE** — Availability, Performance, Quality, and OEE KPIs; OEE by machine center (5 centers, 3 facilities) bar chart from `qad_gold_oee_by_machine_center`.
- **Inventory & Logistics** — Inventory by plant and deliveries by carrier (bar charts).

## Setup

1. **Create virtualenv and install dependencies**
   ```bash
   cd novelis_dashboard
   python3 -m venv .venv
   source .venv/bin/activate   # or .venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

2. **Configure Databricks (optional)**
   - Copy `.env.example` to `.env`.
   - Set `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_WAREHOUSE_ID`, `CATALOG`, `SCHEMA` to point at your workspace and the schema where gold tables live (e.g. `serverless_hadnqm_catalog`, `ai_sc_test`).
   - If these are not set (or `USE_MOCK_DATA=1`), the app uses **mock data** so you can run it without Databricks.

3. **Run locally**
   ```bash
   flask --app app run --host 0.0.0.0 --port 5000
   # or
   python app.py
   ```

4. **Production (Gunicorn)**
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 app:app
   ```

## Environment variables

| Variable | Description |
|----------|-------------|
| `DATABRICKS_HOST` | Workspace URL (e.g. `https://xxx.cloud.databricks.com`) |
| `DATABRICKS_TOKEN` | Personal or workspace access token |
| `DATABRICKS_WAREHOUSE_ID` | SQL warehouse ID for querying gold tables |
| `CATALOG` | Unity Catalog catalog (default: `serverless_hadnqm_catalog`) |
| `SCHEMA` | Schema with gold tables (default: `ai_sc_test`) |
| `USE_MOCK_DATA` | Set to `1` to force mock data |
| `PORT` | Server port (default: 5000) |

## Gold tables used

- **Demand / Supply chain:** `demand`, `procurement`, `inventory`, `logistics` (in the configured catalog/schema).
- **Production OEE:** `qad_gold_oee_by_machine_center` (and optionally `qad_gold_oee_latest`).

## Novelis branding

- **Primary:** Navy `#002855`
- **Secondary:** Blue `#0072CE`, light blue `#00A3E0`
- **Background:** Light gray `#F5F7FA`
- **Cards:** White with subtle shadow and border
