# Databricks notebook source
# MAGIC %md
# MAGIC # Setup SAP-style Delta tables — Aluminum manufacturer
# MAGIC Creates Delta tables with sample data for an aluminum producer: alumina, ingots, coils, extrusions, and related procurement/inventory/manufacturing/logistics/demand.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Config: catalog and schema
# MAGIC Set via job base_parameters (catalog, schema) or Spark config / widget defaults below.

# COMMAND ----------

dbutils.widgets.text("catalog", spark.conf.get("spark.databricks.sap.catalog", "main"), "Catalog")
dbutils.widgets.text("schema", spark.conf.get("spark.databricks.sap.schema", "sap_control_tower"), "Schema")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

# Use existing catalog and schema (do not create)
print(f"Using {catalog}.{schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Procurement (EKKO / EKPO style)
# MAGIC POs for alumina, bauxite, alloying elements, anodes, and packaging.

# COMMAND ----------

procurement_df = spark.createDataFrame([
    ("4500012345", "V-AL-01", "Alumina Corp", "AL-ALUMINA", 500, 185000.0, "Open", "2025-03-01"),
    ("4500012346", "V-AL-02", "Bauxite Mining Co", "AL-BAUXITE", 1200, 96000.0, "Confirmed", "2025-02-28"),
    ("4500012347", "V-AL-03", "Metals Alloy Supply", "ALLOY-MG-SI", 50, 42000.0, "Delivered", "2025-02-15"),
    ("4500012348", "V-AL-01", "Alumina Corp", "AL-ALUMINA", 750, 277500.0, "Open", "2025-03-10"),
    ("4500012349", "V-AL-04", "Carbon Anode Supply", "ANODE-CARBON", 200, 88000.0, "Overdue", "2025-02-10"),
    ("4500012350", "V-AL-05", "Refractory Linings Inc", "REFRACTORY-1", 100, 45000.0, "Confirmed", "2025-03-05"),
], ["ebeln", "lifnr", "vendor_name", "matnr", "menge", "netwr", "status", "eindt"])

procurement_df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.procurement")
display(procurement_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Inventory (MARD / MARC style)
# MAGIC Alumina, primary ingot, coils, billets by plant (smelter, casting, rolling).

# COMMAND ----------

inventory_df = spark.createDataFrame([
    ("AL-ALUMINA", "SMELT-1", "RAW-01", 1200, 50, 500, 800),
    ("AL-INGOT-6061", "CAST-1", "FIN-01", 340, 0, 1200, 500),
    ("AL-COIL-1050", "ROLL-1", "FIN-01", 890, 10, 0, 400),
    ("AL-BILLET-7075", "CAST-1", "FIN-02", 220, 30, 750, 300),
    ("AL-SHEET-2024", "ROLL-1", "FIN-01", 450, 0, 0, 200),
    ("AL-EXTRUSION-6063", "EXTR-1", "FIN-01", 180, 20, 100, 150),
], ["matnr", "werks", "lgort", "unrestricted", "blocked", "in_transit", "reorder_point"])

inventory_df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.inventory")
display(inventory_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Manufacturing (AFPO / AUFK style)
# MAGIC Production orders: casting, rolling, extrusion.

# COMMAND ----------

manufacturing_df = spark.createDataFrame([
    ("1000001", "AL-INGOT-6061", "CAST-1", 1000, "Released", "2025-02-18", "2025-02-22"),
    ("1000002", "AL-COIL-1050", "ROLL-1", 500, "Confirmed", "2025-02-20", "2025-02-25"),
    ("1000003", "AL-INGOT-6061", "CAST-1", 750, "Completed", "2025-02-10", "2025-02-15"),
    ("1000004", "AL-SHEET-2024", "ROLL-1", 2000, "Released", "2025-02-19", "2025-02-28"),
    ("1000005", "AL-EXTRUSION-6063", "EXTR-1", 600, "In Progress", "2025-02-21", "2025-02-26"),
], ["aufnr", "matnr", "werks", "psmng", "status", "gstrs", "gltrs"])

manufacturing_df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.manufacturing")
display(manufacturing_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Logistics (LIKP / LIPS style)
# MAGIC Outbound deliveries: automotive, aerospace, construction, packaging.

# COMMAND ----------

logistics_df = spark.createDataFrame([
    ("8000001234", "CUST-AUTO-01", "AL-COIL-1050", 200, "In Transit", "2025-02-20", "DHL"),
    ("8000001235", "CUST-AERO-02", "AL-SHEET-2024", 150, "Delivered", "2025-02-18", "FedEx"),
    ("8000001236", "CUST-CONST-03", "AL-EXTRUSION-6063", 500, "Pending", "2025-02-25", "UPS"),
    ("8000001237", "CUST-AUTO-01", "AL-INGOT-6061", 100, "In Transit", "2025-02-21", "DHL"),
    ("8000001238", "CUST-PACK-04", "AL-SHEET-2024", 80, "Loaded", "2025-02-22", "XPO"),
], ["vbeln", "kunnr", "matnr", "lfimg", "status", "lfdat", "carrier"])

logistics_df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.logistics")
display(logistics_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Demand / Sales orders (VBAK / VBAP style)
# MAGIC Customer orders and forecast for aluminum products.

# COMMAND ----------

demand_df = spark.createDataFrame([
    ("100001", "CUST-AUTO-01", "AL-COIL-1050", 200, "2025-02-25", "Confirmed", 220),
    ("100002", "CUST-AERO-02", "AL-SHEET-2024", 150, "2025-02-20", "Delivered", 160),
    ("100003", "CUST-CONST-03", "AL-EXTRUSION-6063", 300, "2025-03-05", "Open", 280),
    ("100004", "CUST-PACK-04", "AL-SHEET-2024", 500, "2025-03-15", "Open", 480),
    ("100005", "CUST-AUTO-01", "AL-INGOT-6061", 400, "2025-03-10", "Confirmed", 420),
], ["vbeln", "kunnr", "matnr", "kwmeng", "edatu", "status", "forecast_qty"])

demand_df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.demand")
display(demand_df)

# COMMAND ----------

# MAGIC %md
# MAGIC Done. Tables created (aluminum manufacturer):
# MAGIC - `procurement` — alumina, bauxite, alloys, anodes, refractories
# MAGIC - `inventory` — alumina, ingots, coils, billets, sheet, extrusions by plant
# MAGIC - `manufacturing` — casting, rolling, extrusion orders
# MAGIC - `logistics` — outbound to auto, aero, construction, packaging
# MAGIC - `demand` — sales orders and forecast
# MAGIC
# MAGIC Run **02_control_tower_dashboard** to display the Control Tower UI with this data.
