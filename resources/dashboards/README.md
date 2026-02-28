# Databricks Lakeview dashboards (SAP and QAD gold tables)

Three **Databricks AI/BI (Lakeview) dashboards** are defined here and registered in the bundle. They read from the gold tables in the catalog/schema set in `databricks.yml` (e.g. `serverless_hadnqm_catalog` / `ai_sc_test`).

| Dashboard | Gold tables | Description |
|-----------|-------------|-------------|
| **SAP Orders and Delivery** | `sap_gold_kpi_orders`, `sap_gold_kpi_delivery`, `sap_gold_business_orders` | Orders and delivery KPIs and order list |
| **SAP Procurement and Inventory** | `sap_gold_kpi_procurement`, `sap_gold_kpi_inventory`, `sap_gold_business_procurement` | PO and inventory KPIs and procurement table |
| **QAD OEE** | `qad_gold_oee_by_machine_center`, `qad_gold_oee_latest` | OEE by facility/machine center and latest OEE |

## Deploy

1. Set a **SQL warehouse** for the dashboards: in `databricks.yml`, under `targets.dev.variables`, set `warehouse_id` to your SQL warehouse ID (SQL > Warehouses > copy ID), or use a [lookup](https://docs.databricks.com/en/dev-tools/bundles/variables.html#lookup) by warehouse name.
2. Deploy the bundle:
   ```bash
   databricks bundle deploy -t dev
   ```
3. Open **Databricks > Dashboards** to view and run the dashboards.

Dashboard datasets use the bundle’s `dataset_catalog` and `dataset_schema`, so table names in the JSON are unqualified (e.g. `sap_gold_kpi_orders`).

## Edit dashboards

- Change layout or add widgets in the Databricks UI, then run `databricks bundle generate` to pull updates into the `.lvdash.json` files.
- Or edit the `.lvdash.json` files and run `databricks bundle deploy -t dev` (use `--force` if the workspace version differs).
