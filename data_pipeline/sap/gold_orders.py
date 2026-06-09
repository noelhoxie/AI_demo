# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Gold — sap_gold_orders
# MAGIC Order-level totals from silver with business-friendly column names.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

orders_silver = spark.table(f"`{catalog}`.`{schema}`.sap_silver_orders")

sap_gold_orders = (
    orders_silver
    .groupBy("sales_order_number", "customer_number", "order_date", "order_year_month")
    .agg(
        F.count("line_item_number").alias("total_line_items"),
        F.sum("order_quantity").alias("total_quantity"),
        F.sum("net_value_usd").alias("total_net_value_usd"),
        F.first("requested_delivery_date").alias("requested_delivery_date"),
        F.first("rejection_status").alias("rejection_status"),
        F.max(F.col("is_rejected").cast("int")).alias("has_rejections"),
        F.first("sales_organization").alias("sales_organization"),
    )
    .withColumn("has_rejections", F.col("has_rejections").cast("boolean"))
)

sap_gold_orders.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_gold_orders"
)
display(sap_gold_orders.limit(10))
