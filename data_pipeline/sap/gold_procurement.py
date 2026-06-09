# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Gold — sap_gold_procurement
# MAGIC PO-level totals from silver with business-friendly column names.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

proc_silver = spark.table(f"`{catalog}`.`{schema}`.sap_silver_procurement")

sap_gold_procurement = (
    proc_silver
    .groupBy("purchase_order_number", "supplier_number", "company_code", "po_creation_date")
    .agg(
        F.count("po_line_item_number").alias("total_line_items"),
        F.sum("ordered_quantity").alias("total_quantity"),
        F.sum("net_value_usd").alias("total_net_value_usd"),
        F.first("scheduled_delivery_date").alias("scheduled_delivery_date"),
        F.first("plant").alias("plant"),
        F.first("po_type").alias("po_type"),
    )
    .withColumn(
        "avg_unit_price",
        F.when(F.col("total_quantity") > 0, F.col("total_net_value_usd") / F.col("total_quantity")).otherwise(F.lit(None)),
    )
)

sap_gold_procurement.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_gold_procurement"
)
display(sap_gold_procurement.limit(10))
