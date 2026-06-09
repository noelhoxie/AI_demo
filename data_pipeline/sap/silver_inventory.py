# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Silver — sap_silver_inventory
# MAGIC From MARD (storage location stock) with business-friendly column names and derived fields.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

mard = spark.table(f"`{catalog}`.`{schema}`.bronze_mard")

sap_silver_inventory = (
    mard
    .select(
        F.col("matnr").alias("material_number"),
        F.col("werks").alias("plant"),
        F.col("lgort").alias("storage_location"),
        F.col("labst").alias("unrestricted_stock"),
        F.col("speme").alias("blocked_stock"),
        F.col("insme").alias("in_transit_stock"),
        F.col("eisbe").alias("safety_stock_level"),
    )
    .withColumn("total_stock", F.col("unrestricted_stock") + F.col("blocked_stock") + F.col("in_transit_stock"))
    .withColumn("available_stock", F.col("unrestricted_stock") + F.col("in_transit_stock"))
    .withColumn("is_below_safety_stock", F.col("unrestricted_stock") < F.col("safety_stock_level"))
    .withColumn(
        "stock_status",
        F.when(F.col("unrestricted_stock") < F.col("safety_stock_level"), F.lit("Critical"))
        .when(F.col("unrestricted_stock") < F.col("safety_stock_level") * 2, F.lit("Low"))
        .otherwise(F.lit("OK")),
    )
)

sap_silver_inventory.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_silver_inventory"
)
display(sap_silver_inventory.limit(10))
