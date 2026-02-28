# Databricks notebook source
# MAGIC %md
# MAGIC # QAD Manufacturing — Bronze Ingest (QAD Base Tables)
# MAGIC Ingests raw data from QAD manufacturing into bronze Delta tables aligned to **QAD base table** names and structures.
# MAGIC - **wo_mst** — Work Order Master (QAD work order header)
# MAGIC - **jt_mst** — Job Ticket Master (production completions / labor reporting)
# MAGIC - **dt_mst** — Downtime Master (machine downtime events)
# MAGIC Company context: Novelis-style (3 facilities, 5 machine centers).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Config: catalog and schema

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_hadnqm_catalog", "Catalog")
dbutils.widgets.text("schema", "ai_sc_test", "Schema")
catalog = (dbutils.widgets.get("catalog") or "serverless_hadnqm_catalog").strip()
schema = (dbutils.widgets.get("schema") or "ai_sc_test").strip()

# Use existing catalog and schema (do not create)
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType, TimestampType
import datetime

FACILITIES = ["Oswego", "Kennesaw", "Nachterstedt"]
MACHINE_CENTERS = [
    ("Oswego", "Hot_Mill_1"),
    ("Oswego", "Caster_1"),
    ("Kennesaw", "Cold_Mill_1"),
    ("Kennesaw", "Coating_Line_1"),
    ("Nachterstedt", "Slitter_1"),
]
REASON_CODES = ["Unplanned", "Planned_PM", "Changeover", "Material_Wait", "Quality_Check", "Other"]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Bronze: wo_mst (Work Order Master)
# MAGIC QAD base table **wo_mst** — work order header. Fields: wono (work order number), site, line (machine/line), part, qty_ord, ord_status, start_date, due_date, cr_date.

# COMMAND ----------

n_wo = 200
base_ts = datetime.datetime.utcnow() - datetime.timedelta(days=30)
rows_wo = []
for i in range(n_wo):
    fc, mc = MACHINE_CENTERS[i % len(MACHINE_CENTERS)]
    planned_start = base_ts + datetime.timedelta(days=i % 28, hours=(i * 2) % 24)
    planned_end = planned_start + datetime.timedelta(hours=4 + (i % 8))
    ord_status = ["Planned", "Firm_Planned", "Released", "Released", "Closed", "Closed"][i % 6]
    rows_wo.append((
        f"WO-{100000 + i}",
        fc,
        mc,
        f"AL-{['1050','2024','6061','7075','6063'][i % 5]}",
        500 + (i * 17) % 2000,
        ord_status,
        planned_start,
        planned_end,
        planned_start - datetime.timedelta(days=2),
    ))

wo_mst_schema = StructType([
    StructField("wono", StringType()),
    StructField("site", StringType()),
    StructField("line", StringType()),
    StructField("part", StringType()),
    StructField("qty_ord", IntegerType()),
    StructField("ord_status", StringType()),
    StructField("start_date", TimestampType()),
    StructField("due_date", TimestampType()),
    StructField("cr_date", TimestampType()),
])
df = spark.createDataFrame(rows_wo, wo_mst_schema)
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.wo_mst"
)
display(df.limit(10))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Bronze: jt_mst (Job Ticket Master)
# MAGIC QAD base table **jt_mst** — job ticket / production completion. Fields: ticket_id, wono, site, line, good_qty, scrap_qty, start_ts, end_ts.

# COMMAND ----------

n_tx = 400
rows_tx = []
for i in range(n_tx):
    wo_idx = i % n_wo
    fc, mc = MACHINE_CENTERS[wo_idx % len(MACHINE_CENTERS)]
    start_ts = base_ts + datetime.timedelta(days=(i // 10) % 28, hours=(i * 3) % 24)
    end_ts = start_ts + datetime.timedelta(hours=2 + (i % 4))
    good_qty = 100 + (i * 31) % 500
    scrap_qty = (i % 7) * 2
    rows_tx.append((
        f"JT-{200000 + i}",
        f"WO-{100000 + wo_idx}",
        fc,
        mc,
        good_qty,
        scrap_qty,
        start_ts,
        end_ts,
    ))

jt_mst_schema = StructType([
    StructField("ticket_id", StringType()),
    StructField("wono", StringType()),
    StructField("site", StringType()),
    StructField("line", StringType()),
    StructField("good_qty", IntegerType()),
    StructField("scrap_qty", IntegerType()),
    StructField("start_ts", TimestampType()),
    StructField("end_ts", TimestampType()),
])
df = spark.createDataFrame(rows_tx, jt_mst_schema)
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.jt_mst"
)
display(df.limit(10))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Bronze: dt_mst (Downtime Master)
# MAGIC QAD base table **dt_mst** — machine downtime events. Fields: event_id, site, line, start_ts, end_ts, reason_code, reason_desc.

# COMMAND ----------

n_dt = 150
rows_dt = []
for i in range(n_dt):
    fc, mc = MACHINE_CENTERS[i % len(MACHINE_CENTERS)]
    start_ts = base_ts + datetime.timedelta(days=(i // 3) % 28, hours=(i * 5) % 24)
    duration_mins = 15 + (i * 7) % 120
    end_ts = start_ts + datetime.timedelta(minutes=duration_mins)
    reason = REASON_CODES[i % len(REASON_CODES)]
    rows_dt.append((
        f"DT-{300000 + i}",
        fc,
        mc,
        start_ts,
        end_ts,
        reason,
        reason.replace("_", " "),
    ))

dt_mst_schema = StructType([
    StructField("event_id", StringType()),
    StructField("site", StringType()),
    StructField("line", StringType()),
    StructField("start_ts", TimestampType()),
    StructField("end_ts", TimestampType()),
    StructField("reason_code", StringType()),
    StructField("reason_desc", StringType()),
])
df = spark.createDataFrame(rows_dt, dt_mst_schema)
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.dt_mst"
)
display(df.limit(10))

# COMMAND ----------

# MAGIC %md
# MAGIC QAD base tables created in `{catalog}.{schema}`:
# MAGIC - **wo_mst** — Work Order Master (wono, site, line, part, qty_ord, ord_status, start_date, due_date, cr_date)
# MAGIC - **jt_mst** — Job Ticket Master (ticket_id, wono, site, line, good_qty, scrap_qty, start_ts, end_ts)
# MAGIC - **dt_mst** — Downtime Master (event_id, site, line, start_ts, end_ts, reason_code, reason_desc)
# MAGIC
# MAGIC Run **02_qad_silver_production** next for silver streaming tables.
