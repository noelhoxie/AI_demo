# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Gold — sap_gold_inventory
# MAGIC Inventory summary by material/plant with business-friendly column names.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

inv_silver = spark.table(f"`{catalog}`.`{schema}`.sap_silver_inventory")

sap_gold_inventory = (
    inv_silver
    .groupBy("material_number", "plant")
    .agg(
        F.sum("unrestricted_stock").alias("unrestricted_stock"),
        F.sum("blocked_stock").alias("blocked_stock"),
        F.sum("in_transit_stock").alias("in_transit_stock"),
        F.sum("safety_stock_level").alias("safety_stock_level"),
        F.sum("available_stock").alias("available_stock"),
        F.sum("total_stock").alias("total_stock"),
    )
    .withColumn(
        "inventory_health",
        F.when(F.col("unrestricted_stock") < F.col("safety_stock_level"), F.lit("Critical"))
        .when(F.col("unrestricted_stock") < F.col("safety_stock_level") * 2, F.lit("Low"))
        .otherwise(F.lit("OK")),
    )
)

sap_gold_inventory.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_gold_inventory"
)
display(sap_gold_inventory.limit(10))
