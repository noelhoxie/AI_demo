# Databricks notebook source
# MAGIC %md
# MAGIC # Expro Schema — Create & Populate Delta Tables
# MAGIC Creates and populates all tables in the `expro` schema for the **Expro Intelligence Platform** app.
# MAGIC
# MAGIC **Tables created:**
# MAGIC - `expro_rigs` — 20 global rigs with status, health, and crew data
# MAGIC - `expro_equipment` — per-rig equipment with health scores and failure probabilities
# MAGIC - `expro_anomalies` — active sensor anomalies with z-scores and severity
# MAGIC - `expro_work_orders` — maintenance work orders by rig and priority
# MAGIC - `expro_sop_chunks` — SOP procedure text for Vector Search index
# MAGIC
# MAGIC **After running this notebook**, create a Vector Search index on `expro_sop_chunks`
# MAGIC pointing at the `content` column using the `expro-sop-search` endpoint.

# COMMAND ----------

dbutils.widgets.text("catalog", "demo_nah_catalog", "Catalog")
dbutils.widgets.text("schema",  "expro",            "Schema")
catalog = (dbutils.widgets.get("catalog") or "demo_nah_catalog").strip()
schema  = (dbutils.widgets.get("schema")  or "expro").strip()
print(f"Target: {catalog}.{schema}")

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`")
print(f"Schema {catalog}.{schema} ready")

# COMMAND ----------
# MAGIC %md ## 1. expro_rigs

# COMMAND ----------

import random
from datetime import date, timedelta

random.seed(42)

RIG_SPECS = [
    ("EX-001", "Expro Endeavour",    "FPSO",           "Gulf of Mexico",  28.45, -89.73),
    ("EX-002", "Expro Pioneer",      "Jack-up",        "Gulf of Mexico",  27.92, -92.18),
    ("EX-003", "Expro Frontier",     "Semi-sub",       "Gulf of Mexico",  26.55, -90.41),
    ("EX-004", "Expro Ranger",       "Drillship",      "Gulf of Mexico",  29.12, -87.65),
    ("EX-005", "Expro Atlantic",     "FPSO",           "Gulf of Mexico",  27.30, -94.22),
    ("EX-006", "Expro Viking",       "Semi-sub",       "North Sea",       57.82,   1.34),
    ("EX-007", "Expro Norseman",     "Jack-up",        "North Sea",       56.45,   3.21),
    ("EX-008", "Expro Britannia",    "FPSO",           "North Sea",       58.11,   1.55),
    ("EX-009", "Expro Magnus",       "Fixed Platform", "North Sea",       59.44,   1.86),
    ("EX-010", "Expro Orion",        "Semi-sub",       "Middle East",     24.65,  53.88),
    ("EX-011", "Expro Falcon",       "Jack-up",        "Middle East",     25.91,  56.34),
    ("EX-012", "Expro Phoenix",      "FPSO",           "Middle East",     22.78,  59.12),
    ("EX-013", "Expro Arabia",       "Fixed Platform", "Middle East",     26.30,  51.44),
    ("EX-014", "Expro Caspian",      "Semi-sub",       "Middle East",     40.20,  50.12),
    ("EX-015", "Expro Malabo",       "FPSO",           "West Africa",      3.75,   8.78),
    ("EX-016", "Expro Bonny",        "Jack-up",        "West Africa",      3.31,   7.22),
    ("EX-017", "Expro Niger",        "Semi-sub",       "West Africa",      4.88,   5.44),
    ("EX-018", "Expro Natuna",       "FPSO",           "Southeast Asia",   3.92, 108.33),
    ("EX-019", "Expro Borneo",       "Jack-up",        "Southeast Asia",   5.12, 115.22),
    ("EX-020", "Expro Malay",        "Semi-sub",       "Southeast Asia",   5.55, 112.44),
]

STATUS_CYCLE = [
    "operational","operational","operational","maintenance",
    "maintenance","critical","offline","operational",
    "operational","maintenance","critical","operational",
    "operational","operational","maintenance","operational",
    "operational","operational","maintenance","operational",
]

rigs_data = []
for i, (rig_id, name, rig_type, region, lat, lon) in enumerate(RIG_SPECS):
    status = STATUS_CYCLE[i]
    health = (
        random.randint(75, 98) if status == "operational"
        else random.randint(45, 74) if status == "maintenance"
        else random.randint(15, 44) if status == "critical"
        else random.randint(0,  20)
    )
    last_insp   = (date.today() - timedelta(days=random.randint(10, 180))).isoformat()
    active_wo   = random.randint(0, 8) if status != "offline" else 0
    water_depth = random.randint(50, 3000)
    crew        = random.randint(60, 220)
    rigs_data.append((rig_id, name, rig_type, region, lat, lon,
                      status, health, crew, water_depth, active_wo, last_insp))

rigs_schema = """
    rig_id            STRING,
    rig_name          STRING,
    rig_type          STRING,
    region            STRING,
    lat               DOUBLE,
    lon               DOUBLE,
    status            STRING,
    health_score      INT,
    crew_count        INT,
    water_depth_ft    INT,
    active_work_orders INT,
    last_inspection   DATE
"""

rigs_df = spark.createDataFrame(rigs_data, rigs_schema)
rigs_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.expro_rigs")
print(f"expro_rigs: {rigs_df.count()} rows")
display(rigs_df)

# COMMAND ----------
# MAGIC %md ## 2. expro_equipment

# COMMAND ----------

random.seed(42)

EQUIPMENT_TYPES = [
    "Centrifugal Pump", "BOP Stack", "Riser System", "Wellhead Assembly",
    "Mud Pump", "Top Drive", "Drawworks", "SCR Panel", "Generator", "Gas Compressor",
]

# Rebuild rig health lookup (same seed, same values)
random.seed(42)
rig_health = {}
for i, (rig_id, _, _, _, _, _) in enumerate(RIG_SPECS):
    status = STATUS_CYCLE[i]
    health = (
        random.randint(75, 98) if status == "operational"
        else random.randint(45, 74) if status == "maintenance"
        else random.randint(15, 44) if status == "critical"
        else random.randint(0,  20)
    )
    rig_health[rig_id] = health
    random.randint(10, 180)  # consume last_inspection random
    if status != "offline":
        random.randint(0, 8)   # consume active_wo random
    random.randint(50, 3000)   # water_depth
    random.randint(60, 220)    # crew_count

eq_data = []
eq_id_num = 1000
random.seed(42)
# Regenerate rig health fresh under equipment seed
random.seed(42)
rig_h_for_eq = {}
for i, (rig_id, _, _, _, _, _) in enumerate(RIG_SPECS):
    st = STATUS_CYCLE[i]
    h  = (random.randint(75, 98) if st == "operational"
          else random.randint(45, 74) if st == "maintenance"
          else random.randint(15, 44) if st == "critical"
          else random.randint(0,  20))
    rig_h_for_eq[rig_id] = h
    random.randint(10, 180)
    if st != "offline": random.randint(0, 8)
    random.randint(50, 3000)
    random.randint(60, 220)

random.seed(1001)  # equipment-specific seed
for rig_id, _, _, _, _, _ in RIG_SPECS:
    rig_h = rig_h_for_eq[rig_id]
    for _ in range(random.randint(4, 8)):
        eq_type = random.choice(EQUIPMENT_TYPES)
        health  = min(100, max(5, rig_h + random.randint(-20, 20)))
        fail_7d = max(0.001, round((100 - health) * random.uniform(0.005, 0.012), 3))
        last_svc = (date.today() - timedelta(days=random.randint(5, 365))).isoformat()
        eq_data.append((f"EQ-{eq_id_num}", rig_id, eq_type, health, float(fail_7d), last_svc))
        eq_id_num += 1

eq_schema = """
    equipment_id        STRING,
    rig_id              STRING,
    equipment_type      STRING,
    health_score        INT,
    failure_probability DOUBLE,
    last_service_date   DATE
"""

eq_df = spark.createDataFrame(eq_data, eq_schema)
eq_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.expro_equipment")
print(f"expro_equipment: {eq_df.count()} rows")
display(eq_df.limit(10))

# COMMAND ----------
# MAGIC %md ## 3. expro_anomalies

# COMMAND ----------

from datetime import datetime

SENSORS_MAP = {
    "Vibration":  "VIBRATION",
    "Temperature":"TEMPERATURE",
    "Pressure":   "PRESSURE",
    "RPM":        "RPM",
    "Flow Rate":  "FLOW_RATE",
    "Current":    "CURRENT",
}
SENSORS = list(SENSORS_MAP.keys())

random.seed(2002)  # anomalies-specific seed

# Pull equipment list from Delta so we use the saved rows
eq_rows = eq_df.select("equipment_id", "rig_id", "health_score").collect()

an_data = []
an_id   = 1
for row in eq_rows:
    eq_id_str = row["equipment_id"]
    rig_id    = row["rig_id"]
    health    = row["health_score"]
    if health < 75 or random.random() < 0.3:
        num = random.randint(1, 4) if health < 45 else 1
        for _ in range(num):
            sensor  = random.choice(SENSORS)
            z_score = (round(random.uniform(2.1, 6.5), 2) if health < 45
                       else round(random.uniform(1.5, 3.2), 2))
            trend   = random.choice(["increasing", "increasing", "stable", "decreasing"])
            severity = ("critical" if z_score > 4.0
                        else "high"   if z_score > 3.0
                        else "medium")
            hrs_ago  = random.randint(1, 72)
            det_at   = (datetime.utcnow() - timedelta(hours=hrs_ago)).strftime("%Y-%m-%dT%H:%M:%S")
            value    = round(random.uniform(50, 500), 1)
            acknowledged = False
            an_data.append((
                f"AN-{an_id:04d}", eq_id_str, rig_id,
                SENSORS_MAP[sensor], round(z_score, 2), severity, trend,
                det_at, value, acknowledged,
            ))
            an_id += 1

an_schema = """
    anomaly_id    STRING,
    equipment_id  STRING,
    rig_id        STRING,
    sensor_type   STRING,
    z_score       DOUBLE,
    severity      STRING,
    trend         STRING,
    detected_at   TIMESTAMP,
    value         DOUBLE,
    acknowledged  BOOLEAN
"""

an_df = spark.createDataFrame(an_data, an_schema)
an_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.expro_anomalies")
print(f"expro_anomalies: {an_df.count()} rows")
display(an_df.orderBy("z_score", ascending=False).limit(10))

# COMMAND ----------
# MAGIC %md ## 4. expro_work_orders

# COMMAND ----------

PERSONNEL = [
    "M. Al-Rashid", "J. Thornton", "C. Okonkwo", "P. Andersen",
    "R. MacLeod", "S. Petrov", "L. Santos", "D. Kim", "A. Nwosu", "H. Eriksen",
]
WO_TITLES = [
    "Centrifugal pump seal replacement", "BOP hydraulic pressure test",
    "Riser inspection and recoating",    "Top drive gearbox overhaul",
    "Mud pump liner change",             "Generator load bank test",
    "Gas compressor valve service",      "Drawworks brake lining replacement",
    "SCR panel cooling fan replacement", "Wellhead flange bolt torque check",
]

# Status stored uppercase with underscores; app uses LOWER(REPLACE(status,'_','-'))
# so "OPEN"->"open", "IN_PROGRESS"->"in-progress", "OVERDUE"->"overdue", "COMPLETED"->"completed"
STATUSES_DIST  = ["OPEN","OPEN","OPEN","IN_PROGRESS","IN_PROGRESS","OVERDUE","COMPLETED","COMPLETED"]
PRIORITIES_DIST = ["P1","P1","P2","P2","P2","P3","P3","P3"]

random.seed(3003)  # work-orders-specific seed

wo_data  = []
wo_num   = 4001000
for rig_id, _, _, _, _, _ in RIG_SPECS:
    rig_status = STATUS_CYCLE[RIG_SPECS.index(next(s for s in RIG_SPECS if s[0] == rig_id))]
    if rig_status == "offline":
        continue
    active_wo = rig_h_for_eq.get(rig_id, 0)  # reuse rig health as rough proxy
    n_orders  = max(2, min(8, active_wo // 10 + random.randint(2, 6)))
    for _ in range(n_orders):
        title    = random.choice(WO_TITLES)
        priority = random.choice(PRIORITIES_DIST)
        wo_status = random.choice(STATUSES_DIST)
        if wo_status == "OVERDUE" and priority == "P3":
            priority = "P2"
        due_delta = (timedelta(days=random.randint(-7, 0)) if wo_status == "OVERDUE"
                     else timedelta(days=random.randint(1, 30)))
        due_date     = (date.today() + due_delta).isoformat()
        created_date = (date.today() - timedelta(days=random.randint(1, 60))).isoformat()
        est_h        = random.choice([4, 8, 12, 16, 24, 32, 48])
        actual_h     = round(est_h * random.uniform(0.8, 1.4), 1) if wo_status == "COMPLETED" else None
        eq_pick      = f"EQ-{random.randint(1000, eq_id_num - 1)}"
        wo_data.append((
            f"WO-{wo_num}", rig_id, eq_pick, title,
            priority, wo_status, due_date,
            random.choice(PERSONNEL), est_h, actual_h, created_date,
        ))
        wo_num += 1

wo_schema = """
    work_order_id   STRING,
    rig_id          STRING,
    equipment_id    STRING,
    title           STRING,
    priority        STRING,
    status          STRING,
    due_date        DATE,
    assigned_to     STRING,
    estimated_hours INT,
    actual_hours    DOUBLE,
    created_date    DATE
"""

from pyspark.sql import functions as F

wo_df = spark.createDataFrame(wo_data, wo_schema)
wo_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.expro_work_orders")
print(f"expro_work_orders: {wo_df.count()} rows")
display(wo_df.orderBy(
    F.when(F.col("priority")=="P1",1).when(F.col("priority")=="P2",2).otherwise(3),
    "due_date"
).limit(10))

# COMMAND ----------
# MAGIC %md ## 5. expro_sop_chunks

# COMMAND ----------

SOP_CHUNKS = [
    # BOP-001 §2
    ("SOP-BOP-001-S02", "SOP-BOP-001", "BOP Stack — Critical Anomaly Response",
     "2. Immediate Actions (0–15 minutes)",
     "Step 1: OIM NOTIFICATION — Notify OIM immediately via radio Ch. 16. "
     "Step 2: ALERT DRILLER — Notify Driller and Toolpusher; Driller to drill floor within 5 mins. "
     "Step 3: INITIATE STAND-BY — Halt all well operations. Stop string at nearest safe connection. "
     "Step 4: VISUAL INSPECTION — Check BOP stack and hydraulic manifold for fluid leaks, "
     "pressure drop >200 psi, abnormal noise. Step 5: SENSOR VALIDATION — confirm with secondary sensor.",
     "[SOP-BOP-001] BOP Stack — Critical Anomaly Response — §2"),
    # BOP-001 §3
    ("SOP-BOP-001-S03", "SOP-BOP-001", "BOP Stack — Critical Anomaly Response",
     "3. BOP Function Test Protocol",
     "Annular Preventer Test: Apply 200 psi low-pressure test (hold 5 min), then rated WP (hold 15 min). "
     "Ram Preventer Test: Close rams, low/high pressure test per API RP 53. "
     "FAIL CRITERIA: isolate failed component immediately; notify Company Man within 15 min; "
     "do NOT resume operations; log P1 work order in SAP PM immediately.",
     "[SOP-BOP-001] BOP Stack — Critical Anomaly Response — §3"),
    # WC-001 §2
    ("SOP-WC-001-S02", "SOP-WC-001", "Well Control — Emergency Shutdown and Well Kill",
     "2. Kick Detection and Immediate Shut-In",
     "FLOW CHECK: stop pumps, pick up off bottom. If flow observed → shut-in immediately. "
     "SHUT-IN (Soft Method): raise kelly/TDS, close upper Kelly cock, open HCR valve, "
     "close annular preventer, read SIDPP and SICP, record pit gain. "
     "NOTIFY: Toolpusher and OIM immediately. Call 'WELL CONTROL EVENT' on all radio channels.",
     "[SOP-WC-001] Well Control — §2"),
    # WC-001 §4
    ("SOP-WC-001-S04", "SOP-WC-001", "Well Control — Emergency Shutdown and Well Kill",
     "4. Well Kill Methods",
     "DRILLER'S METHOD: circulate out influx at original mud weight (1st circulation), "
     "then circulate kill weight mud (2nd circulation). "
     "WAIT & WEIGHT: calculate kill weight mud = shut-in SIDPP + original MW × TVD × 0.052. "
     "Both methods require continuous pit volume monitoring. Baryte available for rapid MW increase.",
     "[SOP-WC-001] Well Control — §4"),
    # HSE-001 §2
    ("SOP-HSE-001-S02", "SOP-HSE-001", "HSE — H2S Alarm Response",
     "2. Alarm Response by Level",
     "LEVEL 2 (10 ppm): Announce H2S LEVEL 2 ALARM on all channels. "
     "All personnel in affected zone don SCBA. Halt hot work. Non-essential personnel to upwind muster. "
     "LEVEL 3 (25 ppm): MAYDAY H2S LEVEL 3 — GENERAL MUSTER. Evacuate affected zone. "
     "OIM activates Emergency Response Plan Section 5. Account for all personnel.",
     "[SOP-HSE-001] H2S Alarm Response — §2"),
    # HSE-001 §3
    ("SOP-HSE-001-S03", "SOP-HSE-001", "HSE — H2S Alarm Response",
     "3. SCBA Use and Decontamination",
     "SCBA must be worn when entering any zone with confirmed H2S above 10 ppm. "
     "Buddy system mandatory — minimum 2 persons. Duration: 30-min cylinder; swap before 25% gauge. "
     "After exposure: decontaminate with fresh water, complete medical observation for 4 hours. "
     "Complete HSE Incident Report Form within 1 hour.",
     "[SOP-HSE-001] H2S Alarm Response — §3"),
    # DP-001 §2
    ("SOP-DP-001-S02", "SOP-DP-001", "Dynamic Positioning — Failure Response",
     "2. DP Failure Classification and Immediate Response",
     "CLASS 2 ORANGE ALERT: Switch to backup DP system. Announce standby for potential disconnect. "
     "Commence controlled disconnect if position error approaches 50% of WSOG limit. ERRV to close in. "
     "CLASS 3 RED ALERT / DRIVE-OFF: Emergency stop all thrusters. "
     "EMERGENCY DISCONNECT — execute within 30 seconds. Navigate vessel 500m clear of wellhead.",
     "[SOP-DP-001] Dynamic Positioning — §2"),
    # PM-001 §3
    ("SOP-PM-001-S03", "SOP-PM-001", "HP Pump — Inspection and Service",
     "3. Inspection Checklist",
     "Check coupling alignment (<0.05 mm TIR). Inspect impeller for erosion — replace if wear >15%. "
     "Bearing temperatures: ambient +40°C max. Vibration: Zone C alarm at 4.5–7.1 mm/s, "
     "Zone D danger >7.1 mm/s. Test pressure relief valve lift pressure ±3%. "
     "Calibrate discharge pressure transmitter ±0.5%. Grease motor bearings per OEM interval.",
     "[SOP-PM-001] HP Pump Inspection — §3"),
    # EQ-001 §2
    ("SOP-EQ-001-S02", "SOP-EQ-001", "Equipment — High Vibration Anomaly Response",
     "2. Investigation Procedure",
     "Step 1: Confirm reading with secondary sensor or portable vibration analyser. "
     "Step 2: Visual inspection — check baseplate bolts, listen for abnormal noise, check bearing temps. "
     "Step 3: Vibration spectrum analysis — compare to baseline; identify: imbalance (1× rpm), "
     "misalignment (2× rpm), bearing defect (BPFO/BPFI), looseness (sub-harmonics). "
     "CRITICAL (>7σ): Stop equipment immediately; do not restart without Engineering sign-off.",
     "[SOP-EQ-001] High Vibration Response — §2"),
    # EQ-002 §2
    ("SOP-EQ-002-S02", "SOP-EQ-002", "Equipment — High Temperature Anomaly Response",
     "2. Response Procedure",
     "Step 1: Acknowledge alert; record actual temperature from secondary source. "
     "Step 2: Check lubrication system (oil level, cooler), cooling system (water flow, fan), "
     "and whether equipment is operating above design load. "
     "Step 3: Restore cooling/lubrication if fault found. Monitor for 30 minutes. "
     "CRITICAL (>7σ or above trip threshold): Stop equipment immediately. PTW required for restart.",
     "[SOP-EQ-002] High Temperature Response — §2"),
    # WO-001 §2
    ("SOP-WO-001-S02", "SOP-WO-001", "Work Order Management — P1 Escalation",
     "2. P1 Work Order Creation",
     "P1 WO must be created in SAP PM with: Order Type PM01, Priority P1, "
     "exact equipment Functional Location, required start = current time, "
     "required finish within 24 hours (2 hours for BOP, DP, F&G, ESD, LSA). "
     "Notify Onshore Maintenance Manager by telephone. OIM authorises emergency purchases up to $50K. "
     "If parts not in stock: notify Logistics Coordinator immediately.",
     "[SOP-WO-001] P1 Work Order — §2"),
    # WO-001 §3
    ("SOP-WO-001-S03", "SOP-WO-001", "Work Order Management — P1 Escalation",
     "3. Escalation Contacts and Reporting",
     "Escalation chain: Technician → Maintenance Supervisor → Onshore Maintenance Manager → VP Operations. "
     "30-minute update cadence until WO closed. Safety-critical failure must be entered in IRIS+ within 2h. "
     "P1 WOs overdue >4h trigger automatic email to VP Operations and HSE Manager.",
     "[SOP-WO-001] P1 Work Order — §3"),
    # MUD-001 §2
    ("SOP-MUD-001-S02", "SOP-MUD-001", "Mud Pump — Liner and Valve Maintenance",
     "2. Liner Change Procedure",
     "Isolate pump under Mechanical PTW and LOTO. Drain fluid end and flush with fresh water. "
     "Remove piston rod and liner (use OEM liner puller tool; rotate 90° CCW to release). "
     "Inspect bore for scoring, out-of-round, or cracking — replace cylinder body if >0.030 in oversize. "
     "Install new liner, grease outside, rotate 90° CW to lock. Inspect all 6 valves at liner change. "
     "Replace valve/seat showing >25% wear. Return to service: test at low SPM, ramp to full speed.",
     "[SOP-MUD-001] Mud Pump Liner Change — §2"),
    # MUD-001 §3
    ("SOP-MUD-001-S03", "SOP-MUD-001", "Mud Pump — Liner and Valve Maintenance",
     "3. Valve Inspection Criteria",
     "Inspect all valve seats and inserts at every liner change. Reject if: seat face wear >1/16 in, "
     "insert cracking or chipping, spring free length <90% of new. "
     "Track pump hours — schedule liner change every 150–300 pump hours depending on mud abrasivity. "
     "Log all replacements in SAP PM equipment history.",
     "[SOP-MUD-001] Mud Pump Liner Change — §3"),
]

sop_schema = """
    chunk_id     STRING,
    sop_id       STRING,
    sop_title    STRING,
    section      STRING,
    content      STRING,
    source_label STRING
"""

sop_df = spark.createDataFrame(SOP_CHUNKS, sop_schema)
sop_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.expro_sop_chunks")
print(f"expro_sop_chunks: {sop_df.count()} rows")
display(sop_df)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Summary
# MAGIC
# MAGIC | Table | Rows |
# MAGIC |-------|------|
# MAGIC | `expro_rigs` | 20 |
# MAGIC | `expro_equipment` | ~120 |
# MAGIC | `expro_anomalies` | ~180 |
# MAGIC | `expro_work_orders` | ~130 |
# MAGIC | `expro_sop_chunks` | 14 |
# MAGIC
# MAGIC ### Next step — Vector Search index
# MAGIC Run the following in a separate notebook (requires VS endpoint `expro-sop-search` to exist):
# MAGIC
# MAGIC ```python
# MAGIC from databricks.vector_search.client import VectorSearchClient
# MAGIC vsc = VectorSearchClient()
# MAGIC vsc.create_delta_sync_index(
# MAGIC     endpoint_name          = "expro-sop-search",
# MAGIC     source_table_name      = f"{catalog}.{schema}.expro_sop_chunks",
# MAGIC     index_name             = f"{catalog}.{schema}.expro_sop_chunks_index",
# MAGIC     pipeline_type          = "TRIGGERED",
# MAGIC     primary_key            = "chunk_id",
# MAGIC     embedding_source_column = "content",
# MAGIC     embedding_model_endpoint_name = "databricks-gte-large-en",
# MAGIC )
# MAGIC ```

# COMMAND ----------

# Verify row counts across all tables
for tbl in ["expro_rigs", "expro_equipment", "expro_anomalies", "expro_work_orders", "expro_sop_chunks"]:
    n = spark.table(f"`{catalog}`.`{schema}`.{tbl}").count()
    print(f"  {tbl}: {n} rows")
print("Done.")
