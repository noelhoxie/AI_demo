# Databricks notebook source
# MAGIC %md
# MAGIC # Gold Pipeline — Databricks Manufacturing
# MAGIC
# MAGIC Aggregates `demo_nah_catalog.mfg_silver.*` into app-ready gold tables.
# MAGIC Each table maps directly to a Flask API endpoint in the manufacturing app.
# MAGIC
# MAGIC **Tables produced:**
# MAGIC | Gold Table | App Endpoint | Description |
# MAGIC |------------|-------------|-------------|
# MAGIC | `gold.machine_state`    | `/api/live`     | Latest state snapshot per machine |
# MAGIC | `gold.alarms_active`    | `/api/alarms`   | Open alarms with severity + impact |
# MAGIC | `gold.oee_by_shift`     | `/api/oee-trend`| OEE % by shift × line, last 14 shifts |
# MAGIC | `gold.downtime_pareto`  | `/api/downtime` | Downtime minutes by reason, rolling 7d |
# MAGIC | `gold.mtbf_by_machine`  | `/api/downtime` | MTBF / MTTR / failures_ytd per machine |
# MAGIC | `gold.quality_summary`  | `/api/quality`  | FPY, scrap, rework for current shift |
# MAGIC | `gold.defects_by_type`  | `/api/quality`  | Defect type distribution, current shift |

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window


# COMMAND ----------
# MAGIC %md ## 1 — Machine State (drives `/api/live`)
# MAGIC Latest telemetry snapshot joined to latest production event per machine.
# MAGIC The app polls this every 5 seconds for the live floor view.

spark.sql("""
CREATE OR REPLACE TABLE demo_nah_catalog.mfg_gold.machine_state
COMMENT 'Current machine state snapshot — one row per machine. Source for /api/live.'
AS
WITH latest_telemetry AS (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY machine_id ORDER BY ts DESC) AS rn
  FROM demo_nah_catalog.mfg_silver.machine_telemetry
),
latest_event AS (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY machine_id ORDER BY event_ts DESC) AS rn
  FROM demo_nah_catalog.mfg_silver.production_events
),
current_shift_units AS (
  -- Units produced in the most recent open (or latest) shift
  SELECT machine_id,
    MAX(units_count) AS units_this_shift
  FROM demo_nah_catalog.mfg_silver.machine_telemetry
  WHERE shift_id = (
    SELECT shift_id FROM demo_nah_catalog.mfg_silver.shift_records
    WHERE is_open = TRUE ORDER BY start_ts DESC LIMIT 1
  )
  GROUP BY machine_id
)
SELECT
  m.machine_id,
  m.line,
  m.line_name,
  m.product,
  m.name,
  m.description,
  m.target_units_hr,
  m.std_cycle_sec,
  -- State from latest production event
  COALESCE(e.state, 'running')           AS state,
  e.fault_code,
  e.fault_msg,
  e.idle_reason,
  e.maintenance_type,
  -- Live telemetry
  COALESCE(t.oee_pct, 0)                 AS oee_pct,
  t.temp_c,
  COALESCE(t.cycle_time_sec, m.std_cycle_sec) AS cycle_time_sec,
  COALESCE(u.units_this_shift, 0)        AS units_this_shift,
  t.ts                                   AS last_reading_ts,
  e.event_ts                             AS last_event_ts
FROM demo_nah_catalog.mfg_gold.machine_master m
LEFT JOIN latest_event    e ON m.machine_id = e.machine_id AND e.rn = 1
LEFT JOIN latest_telemetry t ON m.machine_id = t.machine_id AND t.rn = 1
LEFT JOIN current_shift_units u ON m.machine_id = u.machine_id
ORDER BY m.line, m.machine_id
""")

count = spark.sql("SELECT COUNT(*) FROM demo_nah_catalog.mfg_gold.machine_state").collect()[0][0]
print(f"gold.machine_state: {count} machines")
spark.sql("SELECT machine_id, line, state, oee_pct, units_this_shift FROM demo_nah_catalog.mfg_gold.machine_state").show(20, truncate=False)

# COMMAND ----------
# MAGIC %md ## 2 — Active Alarms (drives `/api/alarms`)
# MAGIC Open alarms from today's shift plus any unresolved from prior shifts.

spark.sql("""
CREATE OR REPLACE TABLE demo_nah_catalog.mfg_gold.alarms_active
COMMENT 'Active alarms with enriched metadata. Source for /api/alarms.'
AS
SELECT
  alarm_id,
  machine_id,
  machine_name,
  line,
  line_name,
  product,
  severity,
  code,
  message,
  category,
  triggered_ts,
  triggered_min_ago,
  acknowledged,
  ack_ts,
  ack_by,
  impact,
  is_active
FROM demo_nah_catalog.mfg_silver.alarm_events
WHERE is_active = TRUE
  OR (acknowledged = FALSE AND DATE(triggered_ts) >= DATE_SUB(CURRENT_DATE, 1))
ORDER BY
  CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END,
  triggered_ts DESC
""")

count = spark.sql("SELECT COUNT(*) FROM demo_nah_catalog.mfg_gold.alarms_active").collect()[0][0]
print(f"gold.alarms_active: {count} alarms")
spark.sql("SELECT alarm_id, machine_id, severity, code, acknowledged FROM demo_nah_catalog.mfg_gold.alarms_active").show()

# COMMAND ----------
# MAGIC %md ## 3 — OEE by Shift (drives `/api/oee-trend`)
# MAGIC Average OEE per shift per line for the last 14 shifts.

spark.sql("""
CREATE OR REPLACE TABLE demo_nah_catalog.mfg_gold.oee_by_shift
COMMENT 'OEE % aggregated by shift × line. Source for /api/oee-trend.'
AS
WITH shift_machine_oee AS (
  SELECT
    t.shift_id,
    t.shift_period,
    m.line,
    -- Average OEE for running machines only (exclude zeroes from faults)
    AVG(CASE WHEN t.oee_pct > 0 THEN t.oee_pct END) AS avg_oee,
    COUNT(DISTINCT t.machine_id) AS machine_count
  FROM demo_nah_catalog.mfg_silver.machine_telemetry t
  JOIN demo_nah_catalog.mfg_gold.machine_master m ON t.machine_id = m.machine_id
  WHERE t.oee_pct > 0
  GROUP BY t.shift_id, t.shift_period, m.line
),
shift_plant_oee AS (
  SELECT
    t.shift_id,
    t.shift_period,
    'ALL' AS line,
    AVG(CASE WHEN t.oee_pct > 0 THEN t.oee_pct END) AS avg_oee,
    COUNT(DISTINCT t.machine_id) AS machine_count
  FROM demo_nah_catalog.mfg_silver.machine_telemetry t
  WHERE t.oee_pct > 0
  GROUP BY t.shift_id, t.shift_period
),
combined AS (
  SELECT * FROM shift_machine_oee
  UNION ALL
  SELECT * FROM shift_plant_oee
),
-- Pivot to wide format: one row per shift with columns for each line
pivoted AS (
  SELECT
    shift_id,
    shift_period,
    -- Short label for chart x-axis (e.g. "Mon D", "Mon N")
    CONCAT(
      DATE_FORMAT(TO_DATE(SPLIT(shift_id, '-D')[0]), 'EEE'),
      ' ', shift_period
    ) AS shift_label,
    TO_DATE(SPLIT(shift_id, '-D')[0]) AS shift_date,
    ROUND(MAX(CASE WHEN line = 'ALL' THEN avg_oee END), 1) AS plant_oee,
    ROUND(MAX(CASE WHEN line = 'A'   THEN avg_oee END), 1) AS line_a_oee,
    ROUND(MAX(CASE WHEN line = 'B'   THEN avg_oee END), 1) AS line_b_oee,
    ROUND(MAX(CASE WHEN line = 'C'   THEN avg_oee END), 1) AS line_c_oee
  FROM combined
  GROUP BY shift_id, shift_period
)
SELECT *
FROM pivoted
ORDER BY shift_date DESC, shift_period DESC
LIMIT 14
""")

count = spark.sql("SELECT COUNT(*) FROM demo_nah_catalog.mfg_gold.oee_by_shift").collect()[0][0]
print(f"gold.oee_by_shift: {count} shifts")
spark.sql("SELECT shift_label, plant_oee, line_a_oee, line_b_oee, line_c_oee FROM demo_nah_catalog.mfg_gold.oee_by_shift ORDER BY shift_date, shift_period").show()

# COMMAND ----------
# MAGIC %md ## 4 — Downtime Pareto (drives `/api/downtime`)
# MAGIC Downtime minutes by reason category, rolling 7 days.

spark.sql("""
CREATE OR REPLACE TABLE demo_nah_catalog.mfg_gold.downtime_pareto
COMMENT 'Downtime minutes by reason category (rolling 7 days). Source for /api/downtime pareto.'
AS
WITH downtime_events AS (
  SELECT
    downtime_category AS reason,
    COALESCE(duration_minutes, 0) AS downtime_mins
  FROM demo_nah_catalog.mfg_silver.production_events
  WHERE state != 'running'
    AND downtime_category IS NOT NULL
    AND event_ts >= CURRENT_TIMESTAMP - INTERVAL 7 DAYS
    AND duration_minutes IS NOT NULL
),
aggregated AS (
  SELECT
    reason,
    ROUND(SUM(downtime_mins), 0) AS total_minutes
  FROM downtime_events
  GROUP BY reason
),
with_total AS (
  SELECT *, SUM(total_minutes) OVER () AS grand_total
  FROM aggregated
)
SELECT
  reason,
  total_minutes AS minutes,
  ROUND(100.0 * total_minutes / NULLIF(grand_total, 0), 1) AS pct
FROM with_total
ORDER BY total_minutes DESC
""")

count = spark.sql("SELECT COUNT(*) FROM demo_nah_catalog.mfg_gold.downtime_pareto").collect()[0][0]
print(f"gold.downtime_pareto: {count} categories")
spark.sql("SELECT reason, minutes, pct FROM demo_nah_catalog.mfg_gold.downtime_pareto").show()

# COMMAND ----------
# MAGIC %md ## 5 — MTBF by Machine (drives `/api/downtime` mtbf section)
# MAGIC Mean time between failures and mean time to repair per machine, YTD.

spark.sql("""
CREATE OR REPLACE TABLE demo_nah_catalog.mfg_gold.mtbf_by_machine
COMMENT 'MTBF, MTTR, and failure count per machine YTD. Source for /api/downtime mtbf.'
AS
WITH fault_events AS (
  SELECT
    machine_id,
    event_ts   AS fault_start,
    duration_minutes
  FROM demo_nah_catalog.mfg_silver.production_events
  WHERE state = 'fault'
    AND YEAR(event_ts) = YEAR(CURRENT_DATE)
    AND duration_minutes IS NOT NULL  -- resolved faults only
),
fault_gaps AS (
  SELECT
    machine_id,
    fault_start,
    duration_minutes,
    -- Time since previous fault (gap = MTBF proxy)
    LAG(fault_start) OVER (PARTITION BY machine_id ORDER BY fault_start) AS prev_fault_start
  FROM fault_events
),
machine_stats AS (
  SELECT
    machine_id,
    COUNT(*)                                       AS failures_ytd,
    ROUND(AVG(duration_minutes) / 60.0, 2)        AS mttr_hrs,
    ROUND(AVG(
      CASE
        WHEN prev_fault_start IS NOT NULL
          THEN (UNIX_TIMESTAMP(fault_start) - UNIX_TIMESTAMP(prev_fault_start)) / 3600.0
        ELSE NULL
      END
    ), 0) AS mtbf_hrs
  FROM fault_gaps
  GROUP BY machine_id
)
SELECT
  s.machine_id,
  m.line,
  m.name AS machine_name,
  COALESCE(s.mtbf_hrs, 9999)  AS mtbf_hrs,   -- 9999 = no repeated failures yet
  COALESCE(s.mttr_hrs, 0)     AS mttr_hrs,
  COALESCE(s.failures_ytd, 0) AS failures_ytd,
  -- Flag machines with poor MTBF (below 200 hrs)
  (COALESCE(s.mtbf_hrs, 9999) < 200) AS flagged
FROM demo_nah_catalog.mfg_gold.machine_master m
LEFT JOIN machine_stats s ON m.machine_id = s.machine_id
WHERE s.failures_ytd > 0   -- only show machines with recorded failures
ORDER BY s.failures_ytd DESC
""")

count = spark.sql("SELECT COUNT(*) FROM demo_nah_catalog.mfg_gold.mtbf_by_machine").collect()[0][0]
print(f"gold.mtbf_by_machine: {count} machines with failure history")
spark.sql("SELECT machine_id, mtbf_hrs, mttr_hrs, failures_ytd, flagged FROM demo_nah_catalog.mfg_gold.mtbf_by_machine").show()

# COMMAND ----------
# MAGIC %md ## 6 — Quality Summary (drives `/api/quality`)
# MAGIC FPY, scrap rate, rework rate for the current open shift.

spark.sql("""
CREATE OR REPLACE TABLE demo_nah_catalog.mfg_gold.quality_summary
COMMENT 'Quality KPIs for the current shift. Source for /api/quality summary.'
AS
WITH current_shift AS (
  SELECT shift_id FROM demo_nah_catalog.mfg_silver.shift_records
  WHERE is_open = TRUE ORDER BY start_ts DESC LIMIT 1
),
shift_inspections AS (
  SELECT qi.*
  FROM demo_nah_catalog.mfg_silver.quality_inspections qi
  JOIN current_shift cs ON qi.shift_id = cs.shift_id
)
SELECT
  COUNT(*)                                                    AS total_inspected_shift,
  SUM(CASE WHEN result = 'pass'   THEN 1 ELSE 0 END)         AS total_passed_shift,
  SUM(CASE WHEN result = 'fail'   THEN 1 ELSE 0 END)         AS total_scrap_shift,
  SUM(CASE WHEN result = 'rework' THEN 1 ELSE 0 END)         AS total_rework_shift,
  ROUND(100.0 * SUM(CASE WHEN result = 'pass' THEN 1 ELSE 0 END) / COUNT(*), 1) AS first_pass_yield,
  ROUND(100.0 * SUM(CASE WHEN result = 'fail' THEN 1 ELSE 0 END) / COUNT(*), 2) AS scrap_rate_pct,
  ROUND(100.0 * SUM(CASE WHEN result = 'rework' THEN 1 ELSE 0 END) / COUNT(*), 2) AS rework_rate_pct,
  99.0 AS target_fpy
FROM shift_inspections
""")

print("gold.quality_summary:")
spark.sql("SELECT * FROM demo_nah_catalog.mfg_gold.quality_summary").show()

# COMMAND ----------
# MAGIC %md ## 7 — Defects by Type (drives `/api/quality` defects)
# MAGIC Defect type distribution for the current shift, used for the Pareto/donut chart.

spark.sql("""
CREATE OR REPLACE TABLE demo_nah_catalog.mfg_gold.defects_by_type
COMMENT 'Defect type counts by line for current shift. Source for /api/quality defects.'
AS
WITH current_shift AS (
  SELECT shift_id FROM demo_nah_catalog.mfg_silver.shift_records
  WHERE is_open = TRUE ORDER BY start_ts DESC LIMIT 1
),
defects AS (
  SELECT qi.defect_category AS defect_type, qi.line
  FROM demo_nah_catalog.mfg_silver.quality_inspections qi
  JOIN current_shift cs ON qi.shift_id = cs.shift_id
  WHERE qi.result IN ('fail','rework')
    AND qi.defect_category IS NOT NULL
),
counts AS (
  SELECT
    defect_type,
    line,
    COUNT(*) AS count,
    SUM(COUNT(*)) OVER () AS grand_total
  FROM defects
  GROUP BY defect_type, line
)
SELECT
  defect_type,
  line,
  count,
  ROUND(100.0 * count / NULLIF(grand_total, 0), 1) AS pct
FROM counts
ORDER BY count DESC
""")

count = spark.sql("SELECT COUNT(*) FROM demo_nah_catalog.mfg_gold.defects_by_type").collect()[0][0]
print(f"gold.defects_by_type: {count} defect categories")
spark.sql("SELECT defect_type, line, count, pct FROM demo_nah_catalog.mfg_gold.defects_by_type").show()

# COMMAND ----------
# MAGIC %md ## Summary

print("=" * 60)
print("GOLD PIPELINE COMPLETE")
print("=" * 60)
for tbl in ["machine_state","alarms_active","oee_by_shift",
            "downtime_pareto","mtbf_by_machine","quality_summary","defects_by_type"]:
    n = spark.sql(f"SELECT COUNT(*) FROM demo_nah_catalog.mfg_gold.{tbl}").collect()[0][0]
    print(f"  gold.{tbl:<22} {n:>6} rows")

print("\nThe manufacturing app will now serve live data from these tables.")
print("Set SQL_WAREHOUSE_HTTP_PATH in app.yaml to enable gold table queries.")
