# Databricks notebook source
# MAGIC %md
# MAGIC # SAP Bronze — bronze_mard (MARD)
# MAGIC Storage location stock. One notebook per table for pipeline visibility.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql.types import StructType, StructField, StringType, IntegerType

mard_data = [
    ("AL-ALUMINA", "1000", "0001", 1200, 50, 500, 800),
    ("AL-INGOT-6061", "1000", "0001", 340, 0, 1200, 500),
    ("AL-COIL-1050", "1000", "0001", 890, 10, 0, 400),
    ("AL-BILLET-7075", "1000", "0002", 220, 30, 750, 300),
    ("AL-SHEET-2024", "1000", "0001", 450, 0, 0, 200),
    ("AL-EXTRUSION-6063", "2000", "0001", 180, 20, 100, 150),
]
mard_schema = StructType([
    StructField("matnr", StringType()),
    StructField("werks", StringType()),
    StructField("lgort", StringType()),
    StructField("labst", IntegerType()),
    StructField("speme", IntegerType()),
    StructField("insme", IntegerType()),
    StructField("eisbe", IntegerType()),
])
df = spark.createDataFrame(mard_data, mard_schema)
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"`{catalog}`.`{schema}`.bronze_mard")
display(df)
