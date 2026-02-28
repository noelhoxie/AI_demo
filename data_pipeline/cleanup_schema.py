# Databricks notebook source
# MAGIC %md
# MAGIC # Cleanup schema — drop all tables and views
# MAGIC Drops every table and view in the given catalog.schema so the pipeline can repopulate from scratch.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()
print(f"Dropping all tables/views in `{catalog}`.`{schema}`")

# COMMAND ----------

# List all tables (includes views in Unity Catalog SHOW TABLES)
try:
    tables_df = spark.sql(f"SHOW TABLES IN `{catalog}`.`{schema}`")
except Exception as e:
    print(f"No tables or SHOW failed: {e}")
    tables_df = spark.createDataFrame([], "tableName STRING, isTemporary BOOLEAN")

# COMMAND ----------

# Drop each table (Delta tables); use IF EXISTS
from pyspark.sql import Row

dropped = []
for row in tables_df.collect():
    name = row.tableName if hasattr(row, "tableName") else row["tableName"]
    full_name = f"`{catalog}`.`{schema}`.`{name}`"
    try:
        spark.sql(f"DROP TABLE IF EXISTS {full_name}")
        dropped.append(name)
        print(f"Dropped table: {name}")
    except Exception as e:
        try:
            spark.sql(f"DROP VIEW IF EXISTS {full_name}")
            dropped.append(name)
            print(f"Dropped view: {name}")
        except Exception as e2:
            print(f"Skip {name}: {e2}")

# COMMAND ----------

print(f"Done. Dropped {len(dropped)} object(s): {dropped}")
