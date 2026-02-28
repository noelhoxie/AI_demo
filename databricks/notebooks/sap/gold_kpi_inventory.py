# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Gold KPI — sap_gold_kpi_inventory
# MAGIC High-level inventory KPIs: SKU count, total unrestricted/blocked/transit, safety stock, available.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

inv = spark.table(f"`{catalog}`.`{schema}`.sap_gold_business_inventory")

sap_gold_kpi_inventory = inv.agg(
    F.count(F.lit(1)).alias("total_skus"),
    F.countDistinct("matnr").alias("unique_materials"),
    F.countDistinct("werks").alias("unique_plants"),
    F.coalesce(F.sum("unrestricted_qty"), F.lit(0)).alias("total_unrestricted_qty"),
    F.coalesce(F.sum("blocked_qty"), F.lit(0)).alias("total_blocked_qty"),
    F.coalesce(F.sum("in_transit_qty"), F.lit(0)).alias("total_in_transit_qty"),
    F.coalesce(F.sum("safety_stock"), F.lit(0)).alias("total_safety_stock"),
    F.coalesce(F.sum("total_available"), F.lit(0)).alias("total_available_qty"),
).select(
    "total_skus",
    "unique_materials",
    "unique_plants",
    "total_unrestricted_qty",
    "total_blocked_qty",
    "total_in_transit_qty",
    "total_safety_stock",
    "total_available_qty",
)

sap_gold_kpi_inventory.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_gold_kpi_inventory"
)
display(sap_gold_kpi_inventory)
