# Databricks notebook source
# MAGIC %md
# MAGIC # QAD Manufacturing — Gold OEE
# MAGIC Overall Equipment Effectiveness for 5 machine centers across 3 facilities (Novelis-style).
# MAGIC OEE = Availability × Performance × Quality.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Config: catalog and schema

# COMMAND ----------

dbutils.widgets.text("catalog", spark.conf.get("spark.databricks.sap.catalog", "main"), "Catalog")
dbutils.widgets.text("schema", spark.conf.get("spark.databricks.sap.schema", "sap_control_tower"), "Schema")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

# COMMAND ----------

from pyspark.sql import functions as F

# COMMAND ----------

# MAGIC %md
# MAGIC ## OEE inputs from silver
# MAGIC - **Planned production time** (e.g. 24h shift = 1440 min) — configurable per facility/machine.
# MAGIC - **Run time** = planned time − downtime.
# MAGIC - **Availability** = run_time / planned_time.
# MAGIC - **Ideal cycle time** (e.g. seconds per unit) — from standards; here we derive from good_count/run_time for "ideal" rate.
# MAGIC - **Performance** = (total_count × ideal_cycle_time) / run_time, or actual_output / theoretical_max.
# MAGIC - **Quality** = good_count / total_count.
# MAGIC - **OEE** = Availability × Performance × Quality.

# COMMAND ----------

# Planned production minutes per day (e.g. 3 shifts × 8h = 1440 min)
PLANNED_MINUTES_PER_DAY = 1440.0
# Ideal cycle time in seconds per unit (for performance factor); use 1.0 as baseline if not defined
DEFAULT_IDEAL_CYCLE_SEC = 2.0

silver_daily = spark.table(f"{catalog}.{schema}.qad_silver_machine_center_daily")

# COMMAND ----------

gold_oee = (
    silver_daily
    .withColumn("planned_time_minutes", F.lit(PLANNED_MINUTES_PER_DAY))
    .withColumn("run_time_minutes", F.greatest(
        F.col("total_run_time_seconds") / 60.0,
        F.lit(0.0)
    ))
    # Availability: run_time / planned_time (cap at 1.0)
    .withColumn(
        "availability",
        F.least(F.col("run_time_minutes") / F.col("planned_time_minutes"), F.lit(1.0))
    )
    # Total count = good + scrap
    .withColumn("total_count", F.col("good_count") + F.col("scrap_count"))
    # Quality: good / total (avoid div by zero)
    .withColumn(
        "quality",
        F.when(F.col("total_count") > 0, F.col("good_count") / F.col("total_count")).otherwise(F.lit(1.0))
    )
    # Performance: actual output rate vs theoretical (theoretical = run_time_seconds / ideal_cycle_sec)
    .withColumn(
        "theoretical_count",
        F.when(
            F.col("total_run_time_seconds") > 0,
            F.col("total_run_time_seconds") / DEFAULT_IDEAL_CYCLE_SEC
        ).otherwise(F.lit(0.0))
    )
    .withColumn(
        "performance",
        F.when(
            F.col("theoretical_count") > 0,
            F.least(F.col("total_count") / F.col("theoretical_count"), F.lit(1.0))
        ).otherwise(F.lit(1.0))
    )
    # OEE
    .withColumn(
        "oee",
        (F.col("availability") * F.col("performance") * F.col("quality"))
    )
    .select(
        "facility",
        "machine_center",
        "production_date",
        F.round(F.col("availability"), 4).alias("availability"),
        F.round(F.col("performance"), 4).alias("performance"),
        F.round(F.col("quality"), 4).alias("quality"),
        F.round(F.col("oee"), 4).alias("oee"),
        F.round(F.col("planned_time_minutes"), 2).alias("planned_time_minutes"),
        F.round(F.col("run_time_minutes"), 2).alias("run_time_minutes"),
        F.round(F.col("total_downtime_minutes"), 2).alias("downtime_minutes"),
        "good_count",
        "scrap_count",
        "total_count",
    )
)

gold_oee.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{catalog}.{schema}.qad_gold_oee_by_machine_center"
)
display(gold_oee.orderBy("facility", "machine_center", "production_date"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Gold OEE summary (all 5 machine centers, 3 facilities)
# MAGIC Use this table for dashboards and reporting.

# COMMAND ----------

# Optional: create a view for latest OEE by machine center
spark.sql(f"""
  CREATE OR REPLACE VIEW {catalog}.{schema}.qad_gold_oee_latest AS
  SELECT *
  FROM (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY facility, machine_center ORDER BY production_date DESC) AS rn
    FROM {catalog}.{schema}.qad_gold_oee_by_machine_center
  ) sub
  WHERE rn = 1
""")
display(spark.table(f"{catalog}.{schema}.qad_gold_oee_latest"))

# COMMAND ----------

# MAGIC %md
# MAGIC Gold objects created:
# MAGIC - **`qad_gold_oee_by_machine_center`** — OEE (availability, performance, quality, oee) by facility, machine center, and day. Use for trend and dashboard reports.
# MAGIC - **`qad_gold_oee_latest`** — View of latest OEE row per machine center (5 machine centers across 3 facilities: Oswego, Kennesaw, Nachterstedt).
