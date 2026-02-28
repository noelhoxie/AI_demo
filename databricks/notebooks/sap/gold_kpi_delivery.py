# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Gold KPI — sap_gold_kpi_delivery
# MAGIC High-level delivery KPIs: total deliveries, lines, quantity delivered, unique customers.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

delivery = spark.table(f"`{catalog}`.`{schema}`.sap_silver_analyst_delivery")

sap_gold_kpi_delivery = delivery.agg(
    F.countDistinct("vbeln").alias("total_deliveries"),
    F.count(F.lit(1)).alias("total_delivery_lines"),
    F.coalesce(F.sum("lfimg"), F.lit(0)).alias("total_delivered_qty"),
    F.countDistinct("kunnr").alias("unique_customers"),
    F.countDistinct("matnr").alias("unique_materials_delivered"),
).select(
    "total_deliveries",
    "total_delivery_lines",
    "total_delivered_qty",
    "unique_customers",
    "unique_materials_delivered",
)

sap_gold_kpi_delivery.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_gold_kpi_delivery"
)
display(sap_gold_kpi_delivery)
