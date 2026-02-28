# Implementing the Supply Chain Control Tower in Databricks

This folder contains notebooks and instructions to run the **Supply Chain Control Tower** (SAP-style data) **in Databricks** using Delta tables and `displayHTML`.

## Layout

| Asset | Purpose |
|-------|--------|
| `notebooks/01_setup_sap_delta_tables.py` | Creates SAP-style Delta tables (procurement, inventory, manufacturing, logistics, demand). Run once or replace with your own Delta tables. |
| `notebooks/02_control_tower_dashboard.py` | Reads from those Delta tables, builds the JSON payload, and runs `displayHTML(html)` with the Control Tower UI. |
| `notebooks/03_demand_forecast.py` | Optional: aggregates demand from Delta and runs a simple forecast; can write back to Delta. |

The Control Tower HTML file lives at the **repo root**: `supply_chain_control_tower.html`. The dashboard notebook must be able to read this file (see path config below).

## Quick start

1. **Import the repo into Databricks**  
   Use **Repos** or **Workspace** so that the repo root contains `supply_chain_control_tower.html` and the `databricks/notebooks/` folder.

2. **Create a cluster**  
   Any cluster with a recent Databricks runtime (e.g. 13.3 LTS or newer) is fine. No extra libraries required for the dashboard; for advanced forecasting you can add `prophet` or `statsmodels` to the cluster.

3. **Run the setup notebook once**  
   Open `databricks/notebooks/01_setup_sap_delta_tables.py` and run all cells. This creates the `sap_control_tower` schema and sample Delta tables. To use your own SAP data, either:
   - Replace the table creation with your ETL that writes to the same table names and column names (see notebook for exact column names), or  
   - Point the dashboard to your catalog/schema (see below).

4. **Run the dashboard notebook**  
   Open `databricks/notebooks/02_control_tower_dashboard.py`.  
   - Set the **path to the HTML file** if it’s not in the default location. You can set the Spark config `spark.databricks.sap.controlTowerHtml` to the full path, e.g. `/Workspace/Repos/<your-org>/<repo-name>/supply_chain_control_tower.html`, or edit the `html_path` variable in the notebook.  
   - Run all cells. The last cell runs `displayHTML(...)` and renders the Control Tower with data from your Delta tables.

5. **(Optional) Demand forecast**  
   Run `03_demand_forecast.py` to aggregate demand and compute a simple forecast. You can extend it to use Prophet/ARIMA and write to a `demand_forecast` Delta table for the UI or other jobs.

## Configuration (Spark config or notebook variables)

You can override defaults via cluster or job Spark config, or by editing the notebooks:

| Config key | Default | Description |
|------------|---------|-------------|
| `spark.databricks.sap.catalog` | `main` | Unity Catalog catalog for SAP-style tables. |
| `spark.databricks.sap.schema` | `sap_control_tower` | Schema name. |
| `spark.databricks.sap.controlTowerHtml` | `supply_chain_control_tower.html` | Path to the Control Tower HTML file (use full path in Repos). |

## Delta table → UI field mapping

The dashboard maps Delta columns (SAP-style names) to the keys expected by the front-end:

- **procurement**: `ebeln`→po, `lifnr`→vendor, `vendor_name`→vendorName, `matnr`→material, `menge`→qty, `netwr`→value, `status`, `eindt`→delivery  
- **inventory**: `matnr`→material, `werks`→plant, `lgort`→storageLoc, `unrestricted`, `blocked`, `in_transit`→inTransit, `reorder_point`→reorderPoint  
- **manufacturing**: `aufnr`→order, `matnr`→material, `werks`→plant, `psmng`→qty, `status`, `gstrs`→start, `gltrs`→end  
- **logistics**: `vbeln`→delivery, `kunnr`→shipTo, `matnr`→material, `lfimg`→qty, `status`, `lfdat`→planned, `carrier`  
- **demand**: `vbeln`→order, `kunnr`→customer, `matnr`→material, `kwmeng`→qty, `edatu`→requestDate, `status`, `forecast_qty`→forecastQty  

If your SAP export uses the same or similar names, the dashboard will work; otherwise adjust the mapping in `02_control_tower_dashboard.py`.

## Scheduling (Databricks Jobs)

To refresh the Control Tower on a schedule:

1. Create a **Job** with two tasks:  
   - Task 1: Run `01_setup_sap_delta_tables` (or your ETL that populates the Delta tables).  
   - Task 2: Run `02_control_tower_dashboard` (optional; only needed if you want to refresh the HTML view in a job run; for ad-hoc viewing, run the dashboard notebook manually).
2. For **reporting**, it’s usually enough to schedule only the ETL (Task 1). Users then open the dashboard notebook and run it to see the latest Delta data.

## Databricks Asset Bundles (optional)

If you use **Databricks Asset Bundles**, add a `databricks.yml` under `databricks/` (or your bundle root) and define a job that runs the notebooks in order; point the job’s notebook path to `notebooks/01_setup_sap_delta_tables.py` and `notebooks/02_control_tower_dashboard.py` as needed.
