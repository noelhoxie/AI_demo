# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Gold — sap_gold_business_procurement
# MAGIC PO-level totals from silver. One notebook per table for pipeline visibility.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

proc_silver = spark.table(f"`{catalog}`.`{schema}`.sap_silver_analyst_procurement")

sap_gold_business_procurement = (
    proc_silver
    .groupBy("ebeln", "lifnr", "bukrs", "aedat")
    .agg(
        F.count("ebelp").alias("line_count"),
        F.sum("menge").alias("total_qty"),
        F.sum("netwr").alias("total_value"),
        F.first("eindt").alias("delivery_date"),
    )
)
sap_gold_business_procurement.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_gold_business_procurement"
)
display(sap_gold_business_procurement.limit(10))
