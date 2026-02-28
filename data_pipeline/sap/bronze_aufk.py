# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Bronze — bronze_aufk (AUFK)
# MAGIC Production order header. One notebook per table for pipeline visibility.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql.types import StructType, StructField, StringType

aufk_data = [
    ("1000001", "AL-INGOT-6061", "1000", "REL", "2025-02-18", "2025-02-22"),
    ("1000002", "AL-COIL-1050", "1000", "CONF", "2025-02-20", "2025-02-25"),
    ("1000003", "AL-INGOT-6061", "1000", "DLV", "2025-02-10", "2025-02-15"),
    ("1000004", "AL-SHEET-2024", "1000", "REL", "2025-02-19", "2025-02-28"),
    ("1000005", "AL-EXTRUSION-6063", "2000", "REL", "2025-02-21", "2025-02-26"),
]
aufk_schema = StructType([
    StructField("aufnr", StringType()),
    StructField("matnr", StringType()),
    StructField("werks", StringType()),
    StructField("status", StringType()),
    StructField("gstrs", StringType()),
    StructField("gltrs", StringType()),
])
df = spark.createDataFrame(aufk_data, aufk_schema)
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"`{catalog}`.`{schema}`.bronze_aufk")
display(df)
