# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Gold KPI — sap_gold_kpi_orders
# MAGIC High-level order KPIs: total orders, revenue, avg order value, rejection rate, unique customers.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

orders = spark.table(f"`{catalog}`.`{schema}`.sap_gold_orders")

sap_gold_kpi_orders = orders.agg(
    F.count(F.lit(1)).alias("total_orders"),
    F.coalesce(F.sum("total_net_value_usd"), F.lit(0)).alias("total_revenue_usd"),
    F.coalesce(F.sum("total_quantity"), F.lit(0)).alias("total_quantity_ordered"),
    F.countDistinct("customer_number").alias("unique_customers"),
    F.sum("total_line_items").alias("total_line_items"),
    F.coalesce(F.sum(F.col("has_rejections").cast("int")), F.lit(0)).alias("rejected_orders"),
).withColumn(
    "avg_order_value_usd",
    F.when(F.col("total_orders") > 0, F.col("total_revenue_usd") / F.col("total_orders")).otherwise(F.lit(0)),
).withColumn(
    "rejection_rate_pct",
    F.when(F.col("total_orders") > 0, F.round(F.col("rejected_orders") / F.col("total_orders") * 100, 2)).otherwise(F.lit(0)),
).select(
    "total_orders",
    "total_revenue_usd",
    "avg_order_value_usd",
    "total_quantity_ordered",
    "total_line_items",
    "unique_customers",
    "rejected_orders",
    "rejection_rate_pct",
)

sap_gold_kpi_orders.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_gold_kpi_orders"
)
display(sap_gold_kpi_orders)
