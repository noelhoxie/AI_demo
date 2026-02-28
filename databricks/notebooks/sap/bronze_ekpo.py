# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Bronze — bronze_ekpo (EKPO)
# MAGIC Purchasing document item. One notebook per table for pipeline visibility.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType

ekpo_data = [
    ("4500012345", "00010", "AL-ALUMINA", 500, "KG", 185000.0, "1000", "0001", "2025-03-01"),
    ("4500012346", "00010", "AL-BAUXITE", 1200, "KG", 96000.0, "1000", "0001", "2025-02-28"),
    ("4500012347", "00010", "ALLOY-MG-SI", 50, "KG", 42000.0, "1000", "0001", "2025-02-15"),
    ("4500012348", "00010", "AL-ALUMINA", 750, "KG", 277500.0, "1000", "0001", "2025-03-10"),
    ("4500012349", "00010", "ANODE-CARBON", 200, "EA", 88000.0, "1000", "0001", "2025-02-10"),
]
ekpo_schema = StructType([
    StructField("ebeln", StringType()),
    StructField("ebelp", StringType()),
    StructField("matnr", StringType()),
    StructField("menge", IntegerType()),
    StructField("meins", StringType()),
    StructField("netwr", DoubleType()),
    StructField("werks", StringType()),
    StructField("lgort", StringType()),
    StructField("eindt", StringType()),
])
df = spark.createDataFrame(ekpo_data, ekpo_schema)
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"`{catalog}`.`{schema}`.bronze_ekpo")
display(df)
