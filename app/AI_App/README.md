# Supply Chain Dashboard (AI_App)

Production-grade dashboard built from **SAP** and **QAD** gold tables, with comments stored in a **Databricks Postgres** (or any Postgres) database. Clean UI: no icons, KPIs at the top, four tabs covering the main supply chain components.

## Tabs

1. **Orders** — SAP gold: total orders, order value, avg order value, quantity, unique customers; chart: orders by status.
2. **Procurement** — SAP gold: total POs, PO value, avg PO value, unique suppliers; chart: PO value by vendor.
3. **Inventory & Delivery** — SAP gold: inventory KPIs (SKUs, unrestricted/available qty) and delivery KPIs (deliveries, delivered qty); charts: inventory by plant, deliveries by carrier.
4. **Production OEE** — QAD gold: availability, performance, quality, OEE %; chart: OEE by machine center.

Each tab has a **Comments** section. Comments are stored in Postgres and scoped by tab.

## Data sources (Unity Catalog)

- `sap_gold_kpi_orders`, `sap_gold_business_orders`
- `sap_gold_kpi_procurement`, `sap_gold_business_procurement`
- `sap_gold_kpi_inventory`, `sap_gold_business_inventory`
- `sap_gold_kpi_delivery`, `sap_silver_analyst_delivery`
- `qad_gold_oee_by_machine_center`

## Environment

### Databricks (gold data)

- `DATABRICKS_HOST` — workspace URL (e.g. `https://xxx.cloud.databricks.com`)
- `DATABRICKS_TOKEN` — personal or workspace access token
- `DATABRICKS_WAREHOUSE_ID` — SQL warehouse ID
- `CATALOG` — Unity Catalog catalog (default: `serverless_hadnqm_catalog`)
- `SCHEMA` — Schema with gold tables (default: `ai_sc_test`)

### Postgres (comments)

Uses the same env as `db_connection` in the repo root (or standard Postgres env):

- `PGHOST`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`
- `PGPORT` (default `5432`), `PGSSLMODE` (default `require`), `PGAPPNAME` (optional, for schema name)

When `db_connection` is available (repo root), the app uses it (OAuth token support). Otherwise it connects with `psycopg` and the env vars above.

### Optional

- `USE_MOCK_DATA=1` — use mock KPIs and chart data (no Databricks required).
- `PORT` — server port (default `5000`).

## Postgres setup (comments table)

On first use, create the schema and table. Either:

1. **Call the init endpoint once** (with Postgres configured):
   ```bash
   curl http://localhost:5000/api/init-db
   ```
   This creates the schema (if using `db_connection`'s `get_schema_name()`) and the `dashboard_comments` table.

2. **Or create the table yourself** in your Postgres database:
   ```sql
   CREATE TABLE IF NOT EXISTS dashboard_comments (
     id SERIAL PRIMARY KEY,
     tab TEXT NOT NULL,
     content TEXT NOT NULL,
     created_at TIMESTAMPTZ DEFAULT NOW()
   );
   ```
   Use `public.dashboard_comments` if you don't use `PGAPPNAME`/schema from `db_connection`.

## Run locally

```bash
cd AI_App
pip install -r requirements.txt
# Set env (e.g. .env or export)
python app.py
```

Open `http://localhost:5000`. Hit `http://localhost:5000/api/init-db` once if you want the app to create the comments table.

## UI

The UI follows the **clean production dashboards** skill: no icons, text-only navigation and buttons, single sans-serif font, limited palette (primary navy, light gray background, white cards), KPI cards with label above value, and Chart.js with minimal options.
