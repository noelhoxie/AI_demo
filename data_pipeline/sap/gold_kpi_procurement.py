# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Gold KPI — sap_gold_kpi_procurement
# MAGIC High-level procurement KPIs: total POs, total spend, avg PO spend, unique suppliers.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

proc = spark.table(f"`{catalog}`.`{schema}`.sap_gold_procurement")

sap_gold_kpi_procurement = proc.agg(
    F.count(F.lit(1)).alias("total_purchase_orders"),
    F.coalesce(F.sum("total_net_value_usd"), F.lit(0)).alias("total_spend_usd"),
    F.coalesce(F.sum("total_quantity"), F.lit(0)).alias("total_quantity_ordered"),
    F.countDistinct("supplier_number").alias("unique_suppliers"),
    F.sum("total_line_items").alias("total_line_items"),
).withColumn(
    "avg_po_spend_usd",
    F.when(F.col("total_purchase_orders") > 0, F.col("total_spend_usd") / F.col("total_purchase_orders")).otherwise(F.lit(0)),
).withColumn(
    "avg_unit_cost",
    F.when(F.col("total_quantity_ordered") > 0, F.col("total_spend_usd") / F.col("total_quantity_ordered")).otherwise(F.lit(0)),
).select(
    "total_purchase_orders",
    "total_spend_usd",
    "avg_po_spend_usd",
    "total_quantity_ordered",
    "total_line_items",
    "unique_suppliers",
    "avg_unit_cost",
)

sap_gold_kpi_procurement.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_gold_kpi_procurement"
)
display(sap_gold_kpi_procurement)
