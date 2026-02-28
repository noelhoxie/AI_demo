# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Bronze — bronze_likp (LIKP)
# MAGIC Delivery header. One notebook per table for pipeline visibility.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql.types import StructType, StructField, StringType

likp_data = [
    ("8000001234", "CUST-AUTO-01", "2025-02-20", "2025-02-20", "DHL"),
    ("8000001235", "CUST-AERO-02", "2025-02-18", "2025-02-18", "FedEx"),
    ("8000001236", "CUST-CONST-03", "2025-02-25", "", "UPS"),
    ("8000001237", "CUST-AUTO-01", "2025-02-21", "2025-02-21", "DHL"),
    ("8000001238", "CUST-PACK-04", "2025-02-22", "", "XPO"),
]
likp_schema = StructType([
    StructField("vbeln", StringType()),
    StructField("kunnr", StringType()),
    StructField("lfdat", StringType()),
    StructField("wadat_ist", StringType()),
    StructField("tragr", StringType()),
])
df = spark.createDataFrame(likp_data, likp_schema)
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"`{catalog}`.`{schema}`.bronze_likp")
display(df)
