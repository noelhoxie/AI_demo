# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Bronze — bronze_ekko (EKKO)
# MAGIC Purchasing document header. One notebook per table for pipeline visibility.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql.types import StructType, StructField, StringType

ekko_data = [
    ("4500012345", "1000", "V-AL-01", "NB", "ZNB", "2025-02-01"),
    ("4500012346", "1000", "V-AL-02", "NB", "ZNB", "2025-02-02"),
    ("4500012347", "1000", "V-AL-03", "NB", "ZNB", "2025-02-03"),
    ("4500012348", "1000", "V-AL-01", "NB", "ZNB", "2025-02-05"),
    ("4500012349", "1000", "V-AL-04", "NB", "ZNB", "2025-02-06"),
]
ekko_schema = StructType([
    StructField("ebeln", StringType()),
    StructField("bukrs", StringType()),
    StructField("lifnr", StringType()),
    StructField("bstyp", StringType()),
    StructField("bsart", StringType()),
    StructField("aedat", StringType()),
])
df = spark.createDataFrame(ekko_data, ekko_schema)
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"`{catalog}`.`{schema}`.bronze_ekko")
display(df)
