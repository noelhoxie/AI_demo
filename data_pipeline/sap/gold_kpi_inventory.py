# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Gold KPI — sap_gold_kpi_inventory
# MAGIC High-level inventory KPIs: SKU count, stock levels, safety stock coverage, critical SKUs.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

inv = spark.table(f"`{catalog}`.`{schema}`.sap_gold_inventory")

sap_gold_kpi_inventory = inv.agg(
    F.count(F.lit(1)).alias("total_sku_locations"),
    F.countDistinct("material_number").alias("unique_materials"),
    F.countDistinct("plant").alias("unique_plants"),
    F.coalesce(F.sum("unrestricted_stock"), F.lit(0)).alias("total_unrestricted_stock"),
    F.coalesce(F.sum("blocked_stock"), F.lit(0)).alias("total_blocked_stock"),
    F.coalesce(F.sum("in_transit_stock"), F.lit(0)).alias("total_in_transit_stock"),
    F.coalesce(F.sum("safety_stock_level"), F.lit(0)).alias("total_safety_stock_level"),
    F.coalesce(F.sum("available_stock"), F.lit(0)).alias("total_available_stock"),
    F.coalesce(
        F.sum(F.when(F.col("inventory_health") == "Critical", F.lit(1)).otherwise(F.lit(0))), F.lit(0)
    ).alias("critical_sku_count"),
).select(
    "total_sku_locations",
    "unique_materials",
    "unique_plants",
    "total_unrestricted_stock",
    "total_blocked_stock",
    "total_in_transit_stock",
    "total_safety_stock_level",
    "total_available_stock",
    "critical_sku_count",
)

sap_gold_kpi_inventory.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_gold_kpi_inventory"
)
display(sap_gold_kpi_inventory)
