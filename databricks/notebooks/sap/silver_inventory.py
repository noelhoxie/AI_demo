# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Silver — sap_silver_analyst_inventory
# MAGIC From MARD (storage location stock). One notebook per table for pipeline visibility.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

mard = spark.table(f"`{catalog}`.`{schema}`.bronze_mard")

sap_silver_analyst_inventory = (
    mard
    .withColumn("total_stock", F.col("labst") + F.col("speme") + F.col("insme"))
)
sap_silver_analyst_inventory.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_silver_analyst_inventory"
)
display(sap_silver_analyst_inventory.limit(10))
