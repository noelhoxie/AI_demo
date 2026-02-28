# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Gold — sap_gold_business_inventory
# MAGIC Inventory summary by material/plant from silver. One notebook per table for pipeline visibility.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

inv_silver = spark.table(f"`{catalog}`.`{schema}`.sap_silver_analyst_inventory")

sap_gold_business_inventory = (
    inv_silver
    .groupBy("matnr", "werks")
    .agg(
        F.sum("labst").alias("unrestricted_qty"),
        F.sum("speme").alias("blocked_qty"),
        F.sum("insme").alias("in_transit_qty"),
        F.sum("eisbe").alias("safety_stock"),
        (F.sum("labst") + F.sum("insme")).alias("total_available"),
    )
)
sap_gold_business_inventory.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_gold_business_inventory"
)
display(sap_gold_business_inventory.limit(10))
