# Databricks notebook source
# MAGIC %md
# MAGIC # Demand forecast from SAP-style Delta data
# MAGIC Reads demand/sales history from Delta, runs a simple forecast, and (optionally) writes results back to Delta for the Control Tower.

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

dbutils.widgets.text("catalog", spark.conf.get("spark.databricks.sap.catalog", "main"), "Catalog")
dbutils.widgets.text("schema", spark.conf.get("spark.databricks.sap.schema", "sap_control_tower"), "Schema")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load demand and aggregate by material and period
# MAGIC If you have a separate fact table (e.g. sales by month), point to that instead.

# COMMAND ----------

demand_df = spark.table(f"{catalog}.{schema}.demand")

# Build time series: by material and request-date period (e.g. month)
demand_ts = (
    demand_df
    .withColumn("request_month", F.substring(F.col("edatu"), 1, 7))
    .groupBy("matnr", "request_month")
    .agg(
        F.sum("kwmeng").alias("actual_qty"),
        F.avg("forecast_qty").alias("forecast_qty_avg"),
        F.count("*").alias("order_count"),
    )
    .orderBy("matnr", "request_month")
)
display(demand_ts)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Simple forecast: rolling average next period
# MAGIC For production, use MLflow + Prophet or ARIMA; here we use a 1-period shift as placeholder.

# COMMAND ----------

window_spec = Window.partitionBy("matnr").orderBy("request_month")
forecast_df = (
    demand_ts
    .withColumn("prev_qty", F.lag("actual_qty", 1).over(window_spec))
    .withColumn("forecast_qty_simple", F.coalesce(F.col("prev_qty"), F.col("actual_qty")))
    .withColumn("period_type", F.lit("historical"))
)
display(forecast_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## (Optional) Write forecast to Delta
# MAGIC Uncomment to persist; the Control Tower or downstream jobs can read from this table.

# COMMAND ----------

# forecast_df.write.format("delta").mode("overwrite").saveAsTable(f"{catalog}.{schema}.demand_forecast")
# print("Wrote to " + f"{catalog}.{schema}.demand_forecast")

# COMMAND ----------

# MAGIC %md
# MAGIC To use **Prophet** or **statsmodels** for real forecasting, aggregate to a pandas DataFrame by material and date, then run your model and write results back to Delta with `spark.createDataFrame(...).write.saveAsTable(...)`.
