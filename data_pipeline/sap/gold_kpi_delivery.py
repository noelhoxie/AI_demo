# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Gold KPI — sap_gold_kpi_delivery
# MAGIC High-level delivery KPIs: on-time rate, avg variance days, total units delivered.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

delivery = spark.table(f"`{catalog}`.`{schema}`.sap_silver_delivery")

sap_gold_kpi_delivery = delivery.agg(
    F.countDistinct("delivery_number").alias("total_deliveries"),
    F.count(F.lit(1)).alias("total_delivery_lines"),
    F.coalesce(F.sum("delivered_quantity"), F.lit(0)).alias("total_units_delivered"),
    F.countDistinct("customer_number").alias("unique_customers"),
    F.countDistinct("material_number").alias("unique_materials_delivered"),
    F.coalesce(
        F.sum(F.when(F.col("on_time_delivery") == True, F.lit(1)).otherwise(F.lit(0))), F.lit(0)
    ).alias("on_time_deliveries"),
    F.coalesce(
        F.sum(F.when(F.col("on_time_delivery").isNotNull(), F.lit(1)).otherwise(F.lit(0))), F.lit(0)
    ).alias("completed_deliveries"),
    F.round(F.avg("delivery_variance_days"), 1).alias("avg_delivery_variance_days"),
).withColumn(
    "on_time_delivery_rate_pct",
    F.when(
        F.col("completed_deliveries") > 0,
        F.round(F.col("on_time_deliveries") / F.col("completed_deliveries") * 100, 2),
    ).otherwise(F.lit(0)),
).select(
    "total_deliveries",
    "total_delivery_lines",
    "total_units_delivered",
    "unique_customers",
    "unique_materials_delivered",
    "on_time_delivery_rate_pct",
    "avg_delivery_variance_days",
)

sap_gold_kpi_delivery.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_gold_kpi_delivery"
)
display(sap_gold_kpi_delivery)
