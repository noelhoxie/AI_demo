# Supply Chain Dashboard

Production-grade dashboard built from **SAP** and **QAD** gold tables, with comments stored in a **Databricks Postgres** (or any Postgres) database. Clean UI: no icons, KPIs at the top.

## Tabs

1. **Procurement** — SAP gold: total POs, PO value, avg PO value, unique suppliers; chart: PO value by vendor.
2. **Production** — QAD gold: availability, performance, quality, OEE %; charts: OEE by machine center, forecasted OEE by line (next 7 days).
3. **Tariffs** — US tariff rates (Data.gov/USITC HTS) and a 6-month forecast of average tariff rate (bar chart).
4. **Demand** — Search all public Federal Reserve Economic Data (FRED). Enter keywords (e.g. GDP, unemployment, CPI), view search results, and plot any series. Requires `FRED_API_KEY`.
5. **Disruption Simulator** — What-if scenarios: add disruptions (supplier delay, plant outage, demand spike) with severity and optional scope, then run simulation. View Procurement or Production to see the impact. Reset to return to live data.
6. **Weather alerts** — Orders at risk due to weather; propose reassignments.
7. **Weather map** — Forecasted shipping delay by state (choropleth).
8. **Executive summary** — Combined procurement, production, and weather risk.

Each tab has a **Comments** section (where applicable). Comments are stored in Postgres and scoped by tab.

## Weather shipping delays map

The **Weather delays** page (`/weather-delays`) shows a US map of **forecasted shipping delay days** by **state** (choropleth). Data source: **Open-Meteo** (no API key), NOAA GFS forecast for the next 7 days. Each state is shaded by delay (green = 0, yellow = 1, orange = 2, red = 3+). Click a state to see delay and orders due there. Implemented in `weather_delays.py`; results cached 15 minutes.

## Data sources (Unity Catalog)

All tables live in `{CATALOG}.{SCHEMA}` (e.g. `serverless_hadnqm_catalog.ai_sc_test`). The app reads from the following; populate these to make the application live.

### SAP tables (must be populated)

| Table | Purpose | Key columns used by app |
|-------|---------|--------------------------|
| **sap_gold_kpi_orders** | Orders KPIs (totals, averages) | `total_orders`, `total_order_value`, `avg_order_value`, `total_order_qty`, `total_order_lines`, `unique_customers` |
| **sap_gold_business_orders** | Orders by status (chart) | `absta` (status), row count |
| **sap_gold_kpi_procurement** | Procurement KPIs | `total_pos`, `total_po_value`, `avg_po_value`, `total_po_qty`, `total_po_lines`, `unique_suppliers` |
| **sap_gold_business_procurement** | PO value by vendor (chart) | `lifnr` (vendor), `total_value` |

### QAD table (production OEE)

| Table | Purpose | Key columns used by app |
|-------|---------|--------------------------|
| **qad_gold_oee_by_machine_center** | OEE KPIs and chart | `facility`, `machine_center`, `availability`, `performance`, `quality`, `oee` (0–1 or %, app uses as decimal) |

### Summary list (all tables to populate)

1. **sap_gold_kpi_orders**
2. **sap_gold_business_orders**
3. **sap_gold_kpi_procurement**
4. **sap_gold_business_procurement**
5. **qad_gold_oee_by_machine_center**

Upstream silver tables (if you build gold from them in Databricks): `sap_silver_analyst_orders`, `sap_silver_analyst_procurement` feed the corresponding gold tables. QAD gold is built from `qad_silver_machine_center_daily` (see `databricks/notebooks/qad/`).

## Company / branding

To rebrand the app for a different company, edit **`company.py`** in this folder. That file is the single source of truth for:

- **COMPANY_APP_NAME** — Title in the header and page names
- **COMPANY_SUBTITLE** — Line under the title (e.g. data source)
- **COMPANY_PAGE_TITLE_SUFFIX** — Browser tab suffix
- **COMPANY_FOOTER** — Footer text
- **COMPANY_ACTIONS_SUBTITLE** — Subtitle on the Actions page
- **COMPANY_PRIMARY_COLOR** — Header and accent color (hex)

No need to change templates or CSS; they read from `company` in one place.

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
- `FRED_API_KEY` — Federal Reserve Economic Data API key (free at [fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html)) to enable the **Demand** and **Forecasting** tabs. Demand: search all public FRED series and view observations. Forecasting: build a forecast from economic indicators using FRED series; methods include linear trend, last value, exponential smoothing (Holt), and ARIMA (1,1,1). Exponential smoothing and ARIMA require the `statsmodels` package.
- `DATA_GOV_NO_PROXY=1` — If Data.gov tariff data fails with a proxy error (e.g. 403), the app will automatically retry without using the system proxy. Set this to force all Data.gov requests to skip the proxy from the start.

### Approval email (reassignments)

When reassignments are submitted from the Weather alerts page, an approval notification is sent to **noel.hoxie@databricks.com** (link to the Reassignments page). Set these to enable real email; if unset, reassignments are still stored and the link is shown in the UI:

- `MAIL_SERVER` — SMTP host (e.g. `smtp.gmail.com`).
- `MAIL_PORT` — SMTP port (default `587`).
- `MAIL_USE_TLS` — `true` for TLS (default).
- `MAIL_USERNAME` — SMTP login.
- `MAIL_PASSWORD` — SMTP password.
- `MAIL_FROM` — From address (defaults to `MAIL_USERNAME`).

## Postgres setup (comments table)

On first use, create the schema and table. Either:

1. **Call the init endpoint once** (with Postgres configured):
   ```bash
   curl http://localhost:5000/api/init-db
   ```
   This creates the schema (if using `db_connection`’s `get_schema_name()`) and the `dashboard_comments` table.

2. **Or create the table yourself** in your Postgres database:
   ```sql
   CREATE TABLE IF NOT EXISTS dashboard_comments (
     id SERIAL PRIMARY KEY,
     tab TEXT NOT NULL,
     content TEXT NOT NULL,
     created_at TIMESTAMPTZ DEFAULT NOW()
   );
   ```
   Use `public.dashboard_comments` if you don’t use `PGAPPNAME`/schema from `db_connection`.

## Run locally

```bash
cd supply_chain_dashboard
pip install -r requirements.txt
# Set env (e.g. .env or export)
python app.py
```

Open `http://localhost:5000`. Hit `http://localhost:5000/api/init-db` once if you want the app to create the comments table.

## Deploying

### Option 1: Databricks (Asset Bundle)

The repo uses [Databricks Asset Bundles](https://docs.databricks.com/en/dev-tools/bundles/). The app is registered in `databricks.yml` under `resources.apps.supply_chain_dashboard`.

1. **Prerequisites**: [Databricks CLI](https://docs.databricks.com/en/dev-tools/cli/index.html) and auth to the workspace (e.g. `databricks auth login` or `DATABRICKS_HOST` + `DATABRICKS_TOKEN`).

2. **Deploy** from the repo root:
   ```bash
   databricks bundle deploy -t dev
   ```
   This deploys jobs, the app, and other resources to the `dev` target (see `targets.dev` in `databricks.yml`).

3. In the workspace, open **Apps** and run **supply-chain-dashboard**. Attach a SQL warehouse so the app can query gold tables. For Postgres comments, configure the app’s environment with `PGHOST`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` (or use OAuth via `db_connection` if available in the app’s runtime).

### Option 2: Other hosts (e.g. Cloud Run, App Service, VM)

- Build and run the Flask app (e.g. with gunicorn) and set the same environment variables (Databricks + Postgres) in the host’s config.
- Example with gunicorn:
  ```bash
  cd supply_chain_dashboard
  pip install -r requirements.txt
  gunicorn -w 2 -b 0.0.0.0:$PORT --timeout 120 app:app
  ```

### Deploying AI_App

To deploy the **AI_App** folder instead (same app, different folder): either copy `supply_chain_dashboard/app.yaml` into `AI_App/app.yaml`, add an `AI_App` app entry to `databricks.yml` with `source_code_path: AI_App`, then run `databricks bundle deploy -t dev`; or run AI_App locally/on your own host the same way as above, from the `AI_App` directory.

## UI

The UI follows the **clean production dashboards** skill: no icons, text-only navigation and buttons, single sans-serif font, limited palette (primary navy, light gray background, white cards), KPI cards with label above value, and Chart.js with minimal options.
