# Databricks notebook source
# MAGIC %md
# MAGIC # QAD Manufacturing — Silver streaming tables
# MAGIC Joins QAD base tables (**wo_mst**, **jt_mst**, **dt_mst**) into silver production and downtime tables for OEE.

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()

# COMMAND ----------

from pyspark.sql import functions as F

# COMMAND ----------

# MAGIC %md
# MAGIC ## Silver: Production events (jt_mst + wo_mst join)
# MAGIC One row per job ticket with work order context. Source: QAD **jt_mst**, **wo_mst**.

# COMMAND ----------

wo_mst = spark.table(f"`{catalog}`.`{schema}`.wo_mst")
jt_mst = spark.table(f"`{catalog}`.`{schema}`.jt_mst")

silver_production = (
    jt_mst
    .alias("jt")
    .join(wo_mst.alias("wo"), F.col("jt.wono") == F.col("wo.wono"), "left")
    .select(
        F.col("jt.ticket_id"),
        F.col("jt.wono"),
        F.col("jt.site").alias("facility"),
        F.col("jt.line").alias("machine_center"),
        F.col("jt.good_qty"),
        F.col("jt.scrap_qty"),
        F.col("jt.start_ts"),
        F.col("jt.end_ts"),
        (F.unix_timestamp("jt.end_ts") - F.unix_timestamp("jt.start_ts")).cast("double").alias("run_time_seconds"),
        F.col("wo.part").alias("material"),
        F.col("wo.qty_ord").alias("planned_qty"),
        F.col("wo.ord_status").alias("wo_status"),
    )
)

silver_production.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.qad_silver_production_events"
)
display(silver_production.limit(10))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Silver: Downtime events (from dt_mst)
# MAGIC Cleaned downtime with duration. Source: QAD **dt_mst**.

# COMMAND ----------

dt_mst = spark.table(f"`{catalog}`.`{schema}`.dt_mst")

silver_downtime = (
    dt_mst
    .withColumn(
        "duration_minutes",
        (F.unix_timestamp("end_ts") - F.unix_timestamp("start_ts")) / 60.0
    )
    .select(
        F.col("event_id"),
        F.col("site").alias("facility"),
        F.col("line").alias("machine_center"),
        F.col("start_ts"),
        F.col("end_ts"),
        F.col("duration_minutes"),
        F.col("reason_code"),
        F.col("reason_desc"),
    )
)

silver_downtime.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.qad_silver_downtime_events"
)
display(silver_downtime.limit(10))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Silver: Machine center daily (for OEE)
# MAGIC Aggregated run time, good/scrap, downtime by facility and machine center (day).

# COMMAND ----------

silver_production_events = spark.table(f"`{catalog}`.`{schema}`.qad_silver_production_events")
silver_downtime_events = spark.table(f"`{catalog}`.`{schema}`.qad_silver_downtime_events")

production_by_mc_day = (
    silver_production_events
    .withColumn("production_date", F.to_date("start_ts"))
    .groupBy("facility", "machine_center", "production_date")
    .agg(
        F.sum("run_time_seconds").alias("total_run_time_seconds"),
        F.sum("good_qty").alias("good_count"),
        F.sum("scrap_qty").alias("scrap_count"),
        F.count("*").alias("transaction_count"),
    )
)

downtime_by_mc_day = (
    silver_downtime_events
    .withColumn("production_date", F.to_date("start_ts"))
    .groupBy("facility", "machine_center", "production_date")
    .agg(F.sum("duration_minutes").alias("total_downtime_minutes"))
)

silver_mc_daily = (
    production_by_mc_day
    .join(downtime_by_mc_day, ["facility", "machine_center", "production_date"], "left")
    .withColumn(
        "total_downtime_minutes",
        F.coalesce(F.col("total_downtime_minutes"), F.lit(0.0))
    )
)

silver_mc_daily.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.qad_silver_machine_center_daily"
)
display(silver_mc_daily.limit(10))

# COMMAND ----------

# MAGIC %md
# MAGIC Silver tables created from QAD base tables:
# MAGIC - **qad_silver_production_events** — from **jt_mst** + **wo_mst**
# MAGIC - **qad_silver_downtime_events** — from **dt_mst**
# MAGIC - **qad_silver_machine_center_daily** — daily aggregates for OEE
# MAGIC
# MAGIC Run **03_qad_gold_oee** for OEE by machine center.
