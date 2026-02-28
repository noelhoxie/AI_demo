# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Gold KPI — sap_gold_kpi_orders
# MAGIC High-level order KPIs: total orders, value, avg order value, unique customers.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

orders = spark.table(f"`{catalog}`.`{schema}`.sap_gold_business_orders")

sap_gold_kpi_orders = orders.agg(
    F.count(F.lit(1)).alias("total_orders"),
    F.coalesce(F.sum("total_value"), F.lit(0)).alias("total_order_value"),
    F.coalesce(F.sum("total_qty"), F.lit(0)).alias("total_order_qty"),
    F.countDistinct("kunnr").alias("unique_customers"),
    F.sum("line_count").alias("total_order_lines"),
).withColumn(
    "avg_order_value",
    F.when(F.col("total_orders") > 0, F.col("total_order_value") / F.col("total_orders")).otherwise(F.lit(0)),
).select(
    "total_orders",
    "total_order_value",
    "avg_order_value",
    "total_order_qty",
    "total_order_lines",
    "unique_customers",
)

sap_gold_kpi_orders.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_gold_kpi_orders"
)
display(sap_gold_kpi_orders)
