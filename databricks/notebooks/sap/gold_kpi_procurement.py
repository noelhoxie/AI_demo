# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Gold KPI — sap_gold_kpi_procurement
# MAGIC High-level procurement KPIs: total POs, spend, avg PO value, unique suppliers.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

proc = spark.table(f"`{catalog}`.`{schema}`.sap_gold_business_procurement")

sap_gold_kpi_procurement = proc.agg(
    F.count(F.lit(1)).alias("total_pos"),
    F.coalesce(F.sum("total_value"), F.lit(0)).alias("total_po_value"),
    F.coalesce(F.sum("total_qty"), F.lit(0)).alias("total_po_qty"),
    F.countDistinct("lifnr").alias("unique_suppliers"),
    F.sum("line_count").alias("total_po_lines"),
).withColumn(
    "avg_po_value",
    F.when(F.col("total_pos") > 0, F.col("total_po_value") / F.col("total_pos")).otherwise(F.lit(0)),
).select(
    "total_pos",
    "total_po_value",
    "avg_po_value",
    "total_po_qty",
    "total_po_lines",
    "unique_suppliers",
)

sap_gold_kpi_procurement.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_gold_kpi_procurement"
)
display(sap_gold_kpi_procurement)
