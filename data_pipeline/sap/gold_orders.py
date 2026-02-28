# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Gold — sap_gold_business_orders
# MAGIC Order-level totals from silver. One notebook per table for pipeline visibility.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

orders_silver = spark.table(f"`{catalog}`.`{schema}`.sap_silver_analyst_orders")

sap_gold_business_orders = (
    orders_silver
    .groupBy("vbeln", "kunnr", "audat")
    .agg(
        F.count("posnr").alias("line_count"),
        F.sum("kwmeng").alias("total_qty"),
        F.sum("netwr").alias("total_value"),
        F.first("edatu").alias("request_date"),
        F.first("absta").alias("rejection_status"),
    )
)
sap_gold_business_orders.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_gold_business_orders"
)
display(sap_gold_business_orders.limit(10))
