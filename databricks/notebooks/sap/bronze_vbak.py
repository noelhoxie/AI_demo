# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Bronze — bronze_vbak (VBAK)
# MAGIC Sales document header. One notebook per table for pipeline visibility.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql.types import StructType, StructField, StringType

vbak_data = [
    ("100001", "1000", "10", "00", "CUST-AUTO-01", "2025-02-10"),
    ("100002", "1000", "10", "00", "CUST-AERO-02", "2025-02-11"),
    ("100003", "1000", "10", "00", "CUST-CONST-03", "2025-02-12"),
    ("100004", "1000", "10", "00", "CUST-PACK-04", "2025-02-14"),
    ("100005", "1000", "10", "00", "CUST-AUTO-01", "2025-02-15"),
]
vbak_schema = StructType([
    StructField("vbeln", StringType()),
    StructField("vkorg", StringType()),
    StructField("vtweg", StringType()),
    StructField("spart", StringType()),
    StructField("kunnr", StringType()),
    StructField("audat", StringType()),
])
df = spark.createDataFrame(vbak_data, vbak_schema)
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"`{catalog}`.`{schema}`.bronze_vbak")
display(df)
