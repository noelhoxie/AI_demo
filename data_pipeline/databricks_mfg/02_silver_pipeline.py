# Databricks notebook source
# MAGIC %md
# MAGIC # Silver Pipeline — Databricks Manufacturing
# MAGIC
# MAGIC Transforms `demo_nah_catalog.mfg_bronze.*` into clean, enriched, deduplicated
# MAGIC silver tables. Run this after each bronze chapter drop.
# MAGIC
# MAGIC **Tables produced:**
# MAGIC | Table | Key transform |
# MAGIC |-------|--------------|
# MAGIC | `silver.machine_telemetry` | Deduplicate by (machine_id, ts), validate ranges, add shift_id |
# MAGIC | `silver.production_events` | Compute duration_minutes per state window, enrich from machine master |
# MAGIC | `silver.alarm_events` | Enrich with machine line/product, normalize severity |
# MAGIC | `silver.quality_inspections` | Normalize defect_type, join shift context |
# MAGIC | `silver.shift_records` | Validate timestamps, compute shift_duration_hrs |

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window


# COMMAND ----------
# MAGIC %md ## 1 — Silver: Machine Telemetry

spark.sql("""
CREATE OR REPLACE TABLE demo_nah_catalog.mfg_silver.machine_telemetry
COMMENT 'Validated, deduplicated sensor readings per machine. Enriched with shift_id.'
AS
WITH deduped AS (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY machine_id, ts ORDER BY ingest_ts DESC) AS rn
  FROM demo_nah_catalog.mfg_bronze.machine_telemetry_raw
  WHERE oee_pct    BETWEEN 0 AND 100
    AND temp_c     BETWEEN -50 AND 500
    AND cycle_time_sec > 0
    AND ts IS NOT NULL
    AND machine_id IS NOT NULL
)
SELECT
  machine_id,
  ts,
  oee_pct,
  temp_c,
  cycle_time_sec,
  power_kw,
  units_count,
  -- Assign shift_id: day shift = 06:00-17:59, night shift = 18:00-05:59
  CONCAT(
    DATE_FORMAT(ts, 'yyyy-MM-dd'), '-',
    CASE WHEN HOUR(ts) BETWEEN 6 AND 17 THEN 'D' ELSE 'N' END
  ) AS shift_id,
  CASE WHEN HOUR(ts) BETWEEN 6 AND 17 THEN 'Day' ELSE 'Night' END AS shift_period,
  ingest_ts
FROM deduped
WHERE rn = 1
""")

count = spark.sql("SELECT COUNT(*) FROM demo_nah_catalog.mfg_silver.machine_telemetry").collect()[0][0]
print(f"silver.machine_telemetry: {count:,} rows")

# COMMAND ----------
# MAGIC %md ## 2 — Silver: Production Events

spark.sql("""
CREATE OR REPLACE TABLE demo_nah_catalog.mfg_silver.production_events
COMMENT 'Machine state transitions enriched with machine metadata and duration_minutes.'
AS
WITH enriched AS (
  SELECT
    e.event_id,
    e.machine_id,
    e.event_ts,
    e.state,
    e.fault_code,
    e.fault_msg,
    e.idle_reason,
    e.maintenance_type,
    e.operator_id,
    m.line,
    m.line_name,
    m.product,
    m.name  AS machine_name,
    -- Compute how long the machine stayed in this state
    -- (time until the next event for this machine, or NULL if still current)
    LEAD(e.event_ts) OVER (
      PARTITION BY e.machine_id ORDER BY e.event_ts
    ) AS next_event_ts
  FROM demo_nah_catalog.mfg_bronze.production_events_raw e
  LEFT JOIN demo_nah_catalog.mfg_gold.machine_master m
    ON e.machine_id = m.machine_id
  WHERE e.event_ts IS NOT NULL
    AND e.machine_id IS NOT NULL
    AND e.state IN ('running','fault','idle','maintenance')
),
with_duration AS (
  SELECT *,
    ROUND(
      CASE
        WHEN next_event_ts IS NOT NULL
          THEN (UNIX_TIMESTAMP(next_event_ts) - UNIX_TIMESTAMP(event_ts)) / 60.0
        ELSE NULL  -- still in this state
      END, 1
    ) AS duration_minutes,
    -- Downtime category for pareto analysis
    CASE state
      WHEN 'fault'       THEN 'Equipment Fault'
      WHEN 'idle'        THEN COALESCE(
                               CASE WHEN idle_reason LIKE '%firmware%' OR idle_reason LIKE '%software%'
                                    THEN 'Material / SW Hold'
                                    ELSE 'Other' END, 'Other')
      WHEN 'maintenance' THEN 'Planned Maintenance'
      ELSE NULL
    END AS downtime_category
  FROM enriched
)
SELECT * FROM with_duration
""")

count = spark.sql("SELECT COUNT(*) FROM demo_nah_catalog.mfg_silver.production_events").collect()[0][0]
print(f"silver.production_events: {count:,} rows")

# COMMAND ----------
# MAGIC %md ## 3 — Silver: Alarm Events

spark.sql("""
CREATE OR REPLACE TABLE demo_nah_catalog.mfg_silver.alarm_events
COMMENT 'Alarm events enriched with machine metadata. Severity and category normalized.'
AS
SELECT
  a.alarm_id,
  a.machine_id,
  -- Normalize severity to canonical values
  CASE UPPER(a.severity)
    WHEN 'CRITICAL' THEN 'CRITICAL'
    WHEN 'HIGH'     THEN 'HIGH'
    WHEN 'MEDIUM'   THEN 'MEDIUM'
    ELSE                 'LOW'
  END AS severity,
  a.code,
  a.message,
  a.category,
  a.triggered_ts,
  a.acknowledged,
  a.ack_ts,
  a.ack_by,
  a.impact,
  m.line,
  m.line_name,
  m.product,
  m.name AS machine_name,
  -- Minutes since alarm triggered (useful for recency scoring)
  ROUND((UNIX_TIMESTAMP(CURRENT_TIMESTAMP) - UNIX_TIMESTAMP(a.triggered_ts)) / 60, 0)
    AS triggered_min_ago,
  -- Is this alarm still open (not acknowledged OR acknowledged but not resolved)?
  CASE
    WHEN a.acknowledged = FALSE THEN TRUE
    WHEN a.acknowledged = TRUE AND DATEDIFF(CURRENT_DATE, DATE(a.triggered_ts)) = 0 THEN TRUE
    ELSE FALSE
  END AS is_active,
  a.ingest_ts
FROM demo_nah_catalog.mfg_bronze.alarm_events_raw a
LEFT JOIN demo_nah_catalog.mfg_gold.machine_master m
  ON a.machine_id = m.machine_id
WHERE a.alarm_id IS NOT NULL
  AND a.machine_id IS NOT NULL
  AND a.triggered_ts IS NOT NULL
""")

count = spark.sql("SELECT COUNT(*) FROM demo_nah_catalog.mfg_silver.alarm_events").collect()[0][0]
print(f"silver.alarm_events: {count:,} rows")

# COMMAND ----------
# MAGIC %md ## 4 — Silver: Quality Inspections

spark.sql("""
CREATE OR REPLACE TABLE demo_nah_catalog.mfg_silver.quality_inspections
COMMENT 'Per-unit quality inspection results. Defect types normalized. Shift context joined.'
AS
WITH normalized AS (
  SELECT
    qi.inspection_id,
    qi.unit_serial,
    qi.machine_id,
    qi.line,
    qi.product,
    qi.inspection_ts,
    -- Normalize result
    CASE LOWER(qi.result)
      WHEN 'pass'   THEN 'pass'
      WHEN 'fail'   THEN 'fail'
      WHEN 'rework' THEN 'rework'
      ELSE 'unknown'
    END AS result,
    -- Normalize defect_type to canonical categories
    CASE
      WHEN qi.defect_type LIKE '%Solder%'    THEN 'Solder Bridge'
      WHEN qi.defect_type LIKE '%Bond Wire%' THEN 'Bond Wire Short'
      WHEN qi.defect_type LIKE '%Misalign%'  THEN 'Misalignment'
      WHEN qi.defect_type LIKE '%Contam%'    THEN 'Contamination'
      WHEN qi.defect_type LIKE '%Missing%'   THEN 'Missing Component'
      WHEN qi.defect_type IS NOT NULL        THEN 'Other'
      ELSE NULL
    END AS defect_category,
    qi.shift_id,
    -- Shift period from shift_id suffix
    CASE WHEN qi.shift_id LIKE '%-D' THEN 'Day' ELSE 'Night' END AS shift_period,
    qi.ingest_ts
  FROM demo_nah_catalog.mfg_bronze.quality_inspections_raw qi
  WHERE qi.inspection_id IS NOT NULL
    AND qi.machine_id IS NOT NULL
    AND qi.result IN ('pass','fail','rework')
)
SELECT n.*,
  s.supervisor_id,
  s.start_ts AS shift_start_ts
FROM normalized n
LEFT JOIN (
  SELECT shift_id, supervisor_id, start_ts
  FROM demo_nah_catalog.mfg_bronze.shift_records_raw
  WHERE line = 'ALL'
) s ON n.shift_id = s.shift_id
""")

count = spark.sql("SELECT COUNT(*) FROM demo_nah_catalog.mfg_silver.quality_inspections").collect()[0][0]
print(f"silver.quality_inspections: {count:,} rows")

# COMMAND ----------
# MAGIC %md ## 5 — Silver: Shift Records

spark.sql("""
CREATE OR REPLACE TABLE demo_nah_catalog.mfg_silver.shift_records
COMMENT 'Validated shift records with computed duration and open-shift flag.'
AS
SELECT
  shift_id,
  line,
  product,
  start_ts,
  end_ts,
  supervisor_id,
  target_units,
  -- Duration in hours (NULL if shift is still open)
  ROUND(
    CASE
      WHEN end_ts IS NOT NULL
        THEN (UNIX_TIMESTAMP(end_ts) - UNIX_TIMESTAMP(start_ts)) / 3600.0
      ELSE NULL
    END, 2
  ) AS shift_duration_hrs,
  (end_ts IS NULL) AS is_open,
  CASE WHEN shift_id LIKE '%-D' THEN 'Day' ELSE 'Night' END AS shift_period,
  ingest_ts
FROM demo_nah_catalog.mfg_bronze.shift_records_raw
WHERE start_ts IS NOT NULL
  AND (end_ts IS NULL OR end_ts > start_ts)
  AND line = 'ALL'  -- one record per shift (not per line)
""")

count = spark.sql("SELECT COUNT(*) FROM demo_nah_catalog.mfg_silver.shift_records").collect()[0][0]
print(f"silver.shift_records: {count:,} rows")

# COMMAND ----------
print("\nSilver pipeline complete.")
print("Next: run 03_gold_pipeline.py")
