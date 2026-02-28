# Supply Chain Control Tower (Databricks + PostgreSQL)

Single-page HTML application for a **Supply Chain Control Tower** with five tabs and SAP-style data. Can be deployed in **Databricks** (displayHTML) or run as a **Flask app** backed by **PostgreSQL** using the same connection pattern as the Dash todo app (env-based connection string + optional Databricks OAuth).

## Tabs

| Tab | Function | SAP context |
|-----|----------|-------------|
| **Procurement** | Purchase orders, vendors, PO value | EKKO / EKPO |
| **Inventory** | Stock levels, plants, storage locations, reorder points | MARD / MARC |
| **Manufacturing** | Production orders, plants, quantities, status | AFPO / AUFK |
| **Logistics** | Shipments, deliveries, carriers | LIKP / LIPS |
| **Demand Planning** | Sales orders, forecasts, request dates | VBAK / VBAP |

## Deploy in Databricks

### Option 1: Notebook with `displayHTML`

1. Upload `supply_chain_control_tower.html` to DBFS or workspace files.
2. In a Databricks notebook (Python):

```python
# Read the HTML file (adjust path to your file location)
with open('/Workspace/Users/your@email.com/supply_chain_control_tower.html', 'r') as f:
    html = f.read()

# Optional: inject data from Spark/Databricks SQL (see below)
# html += "<script>window.loadSAPData(" + json.dumps(your_data) + ");</script>"

displayHTML(html)
```

### Option 2: Load real SAP data from Databricks

If your SAP data is in Delta tables or queried via Databricks SQL, build a dict and pass it to `loadSAPData`:

```python
import json

# Example: query your tables and build the same structure as the mock data
procurement = spark.sql("""
  SELECT ebeln AS po, lifnr AS vendor, matnr AS material, menge AS qty, 
         netwr AS value, status, eindt AS delivery
  FROM your_catalog.schema.purchase_orders
""").toPandas().to_dict('records')

# Repeat for inventory, manufacturing, logistics, demand...
data = {
  "procurement": procurement,
  "inventory": [...],
  "manufacturing": [...],
  "logistics": [...],
  "demand": [...]
}

html_base = open('/path/to/supply_chain_control_tower.html').read()
html_base += "<script>window.loadSAPData(" + json.dumps(data) + ");</script>"
displayHTML(html_base)
```

### Option 3: Static asset + iframe

Host the HTML file as a static asset (e.g. Databricks Asset Bundles or a web server). Then embed in a notebook:

```python
iframe_html = '<iframe src="/path/to/supply_chain_control_tower.html" width="100%" height="800"></iframe>'
displayHTML(iframe_html)
```

### Option 4: Databricks notebooks (Delta + displayHTML)

For a **ready-to-run implementation** in Databricks using Delta tables:

1. **Import this repo** into Databricks (Repos or Workspace).
2. **Run once:** `data_pipeline/01_setup_sap_delta_tables.py` — creates SAP-style Delta tables (or use your own).
3. **Run to view:** `data_pipeline/02_control_tower_dashboard.py` — loads from Delta and runs `displayHTML()` with the Control Tower. Set the HTML path (e.g. `/Workspace/Repos/<org>/<repo>/supply_chain_control_tower.html`) if needed.
4. **(Optional)** `data_pipeline/03_demand_forecast.py` — demand aggregation and simple forecast.

See **`data_pipeline/README.md`** for pipeline structure. Use **`databricks.yml`** and Asset Bundles for job scheduling and deployment.

## Flask app with PostgreSQL (same connection as your Dash app)

The connection logic from your Dash todo app is extracted into **db.py** and used by the control tower.

1. Set the same env vars: `PGDATABASE`, `PGUSER`, `PGHOST`, `PGPORT`, `PGSSLMODE`, `PGAPPNAME`. Use `PGPASSWORD` when not in Databricks; in Databricks the app uses OAuth via `databricks.sdk.WorkspaceClient().config.oauth_token().access_token`.
2. Install: `pip install -r requirements.txt`
3. Run: `python app_supply_chain.py`

The app creates schema `{PGAPPNAME}_schema_{PGUSER}` and tables `procurement`, `inventory`, `manufacturing`, `logistics`, `demand`. If empty, it seeds from `build_sap_data()`. Control tower is served at `/` with data from PostgreSQL. Connection string is built in **db.py** as: `dbname={PGDATABASE} user={PGUSER} password={...} host={PGHOST} port={PGPORT} sslmode={PGSSLMODE} application_name={PGAPPNAME}`.

## Files

- **supply_chain_control_tower.html** — Self-contained app (HTML + CSS + JS). Uses mock SAP-style data by default; replace or override via `window.loadSAPData(data)` for live data.

- **db.py** — PostgreSQL connection pool, OAuth refresh, schema/table init, `get_sap_data()` and `seed_sap_data()` for the control tower (same connection pattern as your Dash app).

- **app_supply_chain.py** — Flask app that serves the control tower with data from PostgreSQL.

- **app/** — All app assets: **novelis_dashboard**, **databricks-flask-app**, **AI_App**. See **`app/README.md`**.

- **resources/dashboards/** — Three **Databricks Lakeview dashboards** (SAP Orders & Delivery, SAP Procurement & Inventory, QAD OEE) that display gold table data. Deploy with the bundle after setting `warehouse_id` in `databricks.yml`. See **`resources/dashboards/README.md`**.

- **data_pipeline/** — All data pipelines: SAP bronze/silver/gold notebooks (`sap/`), QAD OEE pipeline (`qad/`), **build_sap_data.py**, **seed_1000_pos.py**, cleanup and setup notebooks. See **`data_pipeline/README.md`**.

- **adient_procurement_app.html** — **Adient procurement app**: raw material cost forecasting and make-buy decisions. Uses demo SAP-style data (MARA, LFA1, EKPO/MBEW price history) for Adient-relevant materials (steel, foam, fabric, plastic, mechanisms).  
  - **Cost forecast**: per-material historical and 6‑month forward forecast (linear trend).  
  - **Make-buy**: compares internal cost vs supplier price and capacity utilization; recommends **Make**, **Buy**, or **Hybrid**.  
  Open in a browser or deploy in Databricks via `displayHTML(open('adient_procurement_app.html').read())`.

## PostgreSQL connection (Dash / Databricks)

- **db_connection.py** — Shared PostgreSQL connection logic: builds connection string from env (`PGDATABASE`, `PGUSER`, `PGHOST`, `PGPORT`, `PGSSLMODE`, `PGAPPNAME`), optional Databricks OAuth token refresh, and connection pool. Use `get_connection()`, `get_schema_name()`, or `get_connection_string()` in any app.
- **app_todo_dash.py** — Todo List Dash app that uses `db_connection` for all DB access (no inline connection code). Run with `python app_todo_dash.py`; set the same env vars (and `PGPASSWORD` locally, or rely on OAuth on Databricks).
