# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Silver — sap_silver_analyst_delivery
# MAGIC LIKP + LIPS join. One notebook per table for pipeline visibility.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

likp = spark.table(f"`{catalog}`.`{schema}`.bronze_likp")
lips = spark.table(f"`{catalog}`.`{schema}`.bronze_lips")

sap_silver_analyst_delivery = (
    lips.alias("p")
    .join(likp.alias("h"), F.col("p.vbeln") == F.col("h.vbeln"), "left")
    .select(
        F.col("p.vbeln"),
        F.col("p.posnr"),
        F.col("p.matnr"),
        F.col("p.lfimg"),
        F.col("p.vrkme"),
        F.col("h.kunnr"),
        F.col("h.lfdat"),
        F.col("h.wadat_ist"),
        F.col("h.tragr"),
    )
)
sap_silver_analyst_delivery.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_silver_analyst_delivery"
)
display(sap_silver_analyst_delivery.limit(10))
