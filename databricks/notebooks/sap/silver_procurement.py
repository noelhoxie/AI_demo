# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Silver — sap_silver_analyst_procurement
# MAGIC EKKO + EKPO join. One notebook per table for pipeline visibility.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql import functions as F

ekko = spark.table(f"`{catalog}`.`{schema}`.bronze_ekko")
ekpo = spark.table(f"`{catalog}`.`{schema}`.bronze_ekpo")

sap_silver_analyst_procurement = (
    ekpo.alias("p")
    .join(ekko.alias("h"), F.col("p.ebeln") == F.col("h.ebeln"), "left")
    .select(
        F.col("p.ebeln"),
        F.col("p.ebelp"),
        F.col("p.matnr"),
        F.col("p.menge"),
        F.col("p.meins"),
        F.col("p.netwr"),
        F.col("p.werks"),
        F.col("p.lgort"),
        F.col("p.eindt"),
        F.col("h.bukrs"),
        F.col("h.lifnr"),
        F.col("h.bsart"),
        F.col("h.aedat"),
    )
)
sap_silver_analyst_procurement.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.sap_silver_analyst_procurement"
)
display(sap_silver_analyst_procurement.limit(10))
