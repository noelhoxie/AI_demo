# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Bronze — bronze_vbap (VBAP)
# MAGIC Sales document item. One notebook per table for pipeline visibility.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType

vbap_data = [
    ("100001", "000010", "AL-COIL-1050", 200, "KG", 2025.0, "2025-02-25", "02"),
    ("100002", "000010", "AL-SHEET-2024", 150, "KG", 1800.0, "2025-02-20", "02"),
    ("100003", "000010", "AL-EXTRUSION-6063", 300, "KG", 3600.0, "2025-03-05", "01"),
    ("100004", "000010", "AL-SHEET-2024", 500, "KG", 6000.0, "2025-03-15", "01"),
    ("100005", "000010", "AL-INGOT-6061", 400, "KG", 4800.0, "2025-03-10", "02"),
]
vbap_schema = StructType([
    StructField("vbeln", StringType()),
    StructField("posnr", StringType()),
    StructField("matnr", StringType()),
    StructField("kwmeng", IntegerType()),
    StructField("vrkme", StringType()),
    StructField("netwr", DoubleType()),
    StructField("edatu", StringType()),
    StructField("absta", StringType()),
])
df = spark.createDataFrame(vbap_data, vbap_schema)
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"`{catalog}`.`{schema}`.bronze_vbap")
display(df)
