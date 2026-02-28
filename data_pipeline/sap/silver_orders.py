# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Silver — sap_silver_analyst_orders
# MAGIC VBAK + VBAP join. One notebook per table for pipeline visibility.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

vbak = spark.table(f"`{catalog}`.`{schema}`.bronze_vbak")
vbap = spark.table(f"`{catalog}`.`{schema}`.bronze_vbap")

sap_silver_analyst_orders = (
    vbap.alias("p")
    .join(vbak.alias("h"), F.col("p.vbeln") == F.col("h.vbeln"), "left")
    .select(
        F.col("p.vbeln"),
        F.col("p.posnr"),
        F.col("p.matnr"),
        F.col("p.kwmeng"),
        F.col("p.vrkme"),
        F.col("p.netwr"),
        F.col("p.edatu"),
        F.col("p.absta"),
        F.col("h.vkorg"),
        F.col("h.vtweg"),
        F.col("h.kunnr"),
        F.col("h.audat"),
    )
)
sap_silver_analyst_orders.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_silver_analyst_orders"
)
display(sap_silver_analyst_orders.limit(10))
