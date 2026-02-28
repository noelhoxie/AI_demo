# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Bronze — bronze_lips (LIPS)
# MAGIC Delivery item. One notebook per table for pipeline visibility.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql.types import StructType, StructField, StringType, IntegerType

lips_data = [
    ("8000001234", "000010", "AL-COIL-1050", 200, "KG"),
    ("8000001235", "000010", "AL-SHEET-2024", 150, "KG"),
    ("8000001236", "000010", "AL-EXTRUSION-6063", 500, "KG"),
    ("8000001237", "000010", "AL-INGOT-6061", 100, "KG"),
    ("8000001238", "000010", "AL-SHEET-2024", 80, "KG"),
]
lips_schema = StructType([
    StructField("vbeln", StringType()),
    StructField("posnr", StringType()),
    StructField("matnr", StringType()),
    StructField("lfimg", IntegerType()),
    StructField("vrkme", StringType()),
])
df = spark.createDataFrame(lips_data, lips_schema)
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"`{catalog}`.`{schema}`.bronze_lips")
display(df)
