# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze Seed Generator — Databricks Manufacturing
# MAGIC
# MAGIC Drops raw data into `demo_nah_catalog.mfg_bronze.*` tables to tell the story
# MAGIC of a single manufacturing shift that starts cleanly and progressively degrades.
# MAGIC
# MAGIC ## How to run
# MAGIC Use the **chapter** widget to control how much of the story is loaded.
# MAGIC Run chapters in sequence, running the silver + gold pipelines between each:
# MAGIC
# MAGIC | Chapter | What drops | Story moment |
# MAGIC |---------|-----------|--------------|
# MAGIC | 1 | 7 days of history | Baseline — plant running well all week |
# MAGIC | 2 | Today 06:00–07:15 | Shift starts clean — all 18 machines up |
# MAGIC | 3 | Today 07:30–12:45 | Crisis unfolds — faults hit one by one |
# MAGIC | 4 | Today 13:00 snapshot | Live state — 3 faults, OEE at 83% |
# MAGIC
# MAGIC After each chapter: run `02_silver_pipeline` → `03_gold_pipeline` → refresh app.

# COMMAND ----------

dbutils.widgets.dropdown("chapter", "1", ["1", "2", "3", "4"], "Story Chapter")
dbutils.widgets.dropdown("reset", "no", ["no", "yes"], "Reset all bronze tables first?")

# COMMAND ----------

import uuid
import math
import random
from datetime import datetime, timedelta, timezone
from pyspark.sql import Row
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType,
    DoubleType, IntegerType, BooleanType
)

CHAPTER = int(dbutils.widgets.get("chapter"))
RESET   = dbutils.widgets.get("reset") == "yes"

# Reference point: today's shift started at 06:00 local
NOW         = datetime.now().replace(tzinfo=timezone.utc)
TODAY       = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
SHIFT_START = TODAY.replace(hour=6)  # 06:00 today

print(f"Chapter: {CHAPTER}  |  Shift start: {SHIFT_START}  |  Now: {NOW}")

# COMMAND ----------
# MAGIC %md ## Machine reference (mirrors api.py MACHINES_STATIC)

MACHINES = [
    # Line A — Photon Fab (PPU)
    {"id":"PPU-FAB-01","line":"A","product":"PPU","base_oee":94.1,"base_temp":22.4,"cycle":8.2,  "target_hr":420},
    {"id":"PPU-FAB-02","line":"A","product":"PPU","base_oee":91.3,"base_temp":45.2,"cycle":12.1, "target_hr":290},
    {"id":"PPU-FAB-03","line":"A","product":"PPU","base_oee":91.5,"base_temp":28.1,"cycle":12.1, "target_hr":290},  # today: fault
    {"id":"PPU-FAB-04","line":"A","product":"PPU","base_oee":88.7,"base_temp":380.0,"cycle":22.0,"target_hr":160},
    {"id":"PPU-FAB-05","line":"A","product":"PPU","base_oee":92.4,"base_temp":31.7,"cycle":4.8,  "target_hr":720},
    {"id":"PPU-FAB-06","line":"A","product":"PPU","base_oee":92.0,"base_temp":23.0,"cycle":4.8,  "target_hr":720},  # today: maintenance
    # Line B — Delta Array (DLA)
    {"id":"DLK-ASM-01","line":"B","product":"DLA","base_oee":89.2,"base_temp":24.8,"cycle":6.4,  "target_hr":540},
    {"id":"DLK-ASM-02","line":"B","product":"DLA","base_oee":93.6,"base_temp":247.3,"cycle":18.0,"target_hr":192},
    {"id":"DLK-ASM-03","line":"B","product":"DLA","base_oee":97.1,"base_temp":23.2,"cycle":3.2,  "target_hr":1080},
    {"id":"DLK-ASM-04","line":"B","product":"DLA","base_oee":88.5,"base_temp":26.1,"cycle":9.5,  "target_hr":368},  # today: idle
    {"id":"DLK-ASM-05","line":"B","product":"DLA","base_oee":85.4,"base_temp":85.0,"cycle":3600, "target_hr":1},
    {"id":"DLK-ASM-06","line":"B","product":"DLA","base_oee":90.2,"base_temp":29.4,"cycle":45.0, "target_hr":78},   # today: fault
    # Line C — Genie AI (GAM)
    {"id":"GEN-INT-01","line":"C","product":"GAM","base_oee":91.8,"base_temp":27.3,"cycle":5.5,  "target_hr":648},
    {"id":"GEN-INT-02","line":"C","product":"GAM","base_oee":88.3,"base_temp":210.5,"cycle":7.2, "target_hr":490},
    {"id":"GEN-INT-03","line":"C","product":"GAM","base_oee":82.1,"base_temp":34.6,"cycle":14.0, "target_hr":252},
    {"id":"GEN-INT-04","line":"C","product":"GAM","base_oee":90.0,"base_temp":31.2,"cycle":30.0, "target_hr":118},  # today: fault
    {"id":"GEN-INT-05","line":"C","product":"GAM","base_oee":90.4,"base_temp":70.2,"cycle":7200, "target_hr":1},
    {"id":"GEN-INT-06","line":"C","product":"GAM","base_oee":96.2,"base_temp":22.8,"cycle":11.0, "target_hr":320},
]

LINE_OEE_MULT = {"A": 1.0, "B": 0.97, "C": 0.96}  # Line A runs slightly hotter than B/C

def uid(): return str(uuid.uuid4())

def oee_for(machine, ts, fault_at=None):
    """OEE with sinusoidal drift and night-shift penalty."""
    hour = ts.hour
    night_penalty = -4.5 if (hour < 6 or hour >= 18) else 0
    phase = math.sin(2 * math.pi * ts.timestamp() / 3600) * 1.8
    val = machine["base_oee"] + night_penalty + phase
    if fault_at and ts >= fault_at:
        val = 0.0
    return round(max(0.0, min(99.9, val)), 1)

def temp_for(machine, ts):
    phase = math.sin(2 * math.pi * ts.timestamp() / 90) * 1.5
    return round(machine["base_temp"] + phase, 1)

def cycle_for(machine, ts):
    phase = math.sin(2 * math.pi * ts.timestamp() / 60) * 0.3
    return round(max(0.5, machine["cycle"] + phase), 2)

def ingest_now():
    return datetime.now(timezone.utc)

# COMMAND ----------
# MAGIC %md ## Optional: Reset bronze tables

if RESET:
    print("Truncating all bronze tables...")
    for tbl in ["machine_telemetry_raw","production_events_raw",
                "alarm_events_raw","quality_inspections_raw","shift_records_raw"]:
        spark.sql(f"DELETE FROM demo_nah_catalog.mfg_bronze.{tbl}")
    print("Reset complete.")

# ══════════════════════════════════════════════════════════════════════════════
# CHAPTER 1 — HISTORICAL BASELINE (Days 1-7)
# ──────────────────────────────────────────────────────────────────────────────
# Story: The Databricks Unit plant has been running for 7 days. Good week overall.
# OEE trends match the app's historical charts. A handful of transient faults
# were quickly resolved. MTBF data accumulates for the reliability analysis.
# Quality is consistent. Night shifts run ~5% below day shifts as expected.
# ══════════════════════════════════════════════════════════════════════════════

if CHAPTER >= 1:
    print("\n─── CHAPTER 1: Loading 7-day historical baseline ───")

    # ── Shift records: 14 shifts over 7 days ──────────────────────────────────
    shift_rows = []
    # Target plant OEEs per shift to match OEE_TREND in api.py:
    # Mon D=84.2, Mon N=81.7, Tue D=86.4, Tue N=83.1,
    # Wed D=87.9, Wed N=82.4, Thu D=83.2, Thu N=80.5,
    # Fri D=85.1, Fri N=80.9, Sat D=83.7, Sat N=80.1,
    # Sun D=84.9, Sun N=81.3
    shifts = [
        (-7, "D", "OP-101", 3850), (-7, "N", "OP-102", 2900),
        (-6, "D", "OP-103", 4100), (-6, "N", "OP-104", 3100),
        (-5, "D", "OP-105", 4300), (-5, "N", "OP-101", 3000),
        (-4, "D", "OP-102", 3950), (-4, "N", "OP-103", 2850),
        (-3, "D", "OP-104", 4050), (-3, "N", "OP-105", 2950),
        (-2, "D", "OP-101", 3900), (-2, "N", "OP-102", 2800),
        (-1, "D", "OP-103", 4150), (-1, "N", "OP-104", 3050),
    ]
    for (day_offset, period, supervisor, target) in shifts:
        day = TODAY + timedelta(days=day_offset)
        s_ts = day.replace(hour=6)  if period == "D" else day.replace(hour=18)
        e_ts = day.replace(hour=18) if period == "D" else (day + timedelta(days=1)).replace(hour=6)
        shift_id = f"{day.strftime('%Y-%m-%d')}-{period}"
        for line in ["ALL", "A", "B", "C"]:
            shift_rows.append(Row(
                shift_id=shift_id, line=line, product=None,
                start_ts=s_ts, end_ts=e_ts,
                supervisor_id=supervisor, target_units=target,
                ingest_ts=ingest_now()
            ))

    spark.createDataFrame(shift_rows).write.mode("append").saveAsTable("demo_nah_catalog.mfg_bronze.shift_records_raw")
    print(f"  Shift records: {len(shift_rows)} rows")

    # ── Machine telemetry: every 15 min for 7 days ────────────────────────────
    telemetry_rows = []
    for day_offset in range(-7, 0):
        day = TODAY + timedelta(days=day_offset)
        ts = day.replace(hour=6)
        end = day.replace(hour=18)  # day shift only for brevity
        while ts <= end:
            for m in MACHINES:
                telemetry_rows.append(Row(
                    machine_id=m["id"], ts=ts,
                    oee_pct=oee_for(m, ts),
                    temp_c=temp_for(m, ts),
                    cycle_time_sec=cycle_for(m, ts),
                    power_kw=round(m["base_oee"] * 0.08 + math.sin(ts.timestamp()/300)*2, 2),
                    units_count=int(m["target_hr"] * ((ts - ts.replace(hour=6,minute=0,second=0)).seconds / 3600)),
                    ingest_ts=ingest_now()
                ))
            ts += timedelta(minutes=15)

    spark.createDataFrame(telemetry_rows).write.mode("append").saveAsTable("demo_nah_catalog.mfg_bronze.machine_telemetry_raw")
    print(f"  Telemetry: {len(telemetry_rows)} rows (7 days × 18 machines × 15-min intervals)")

    # ── Historical production events ──────────────────────────────────────────
    # Each day: all machines start. A few machines fault and recover.
    # Failure distribution matches MACHINE_MTBF in api.py:
    #   PPU-FAB-03: 18 failures/yr (~0.35/week)  → 2-3 this week
    #   DLK-ASM-06: 14 failures/yr                → 2 this week
    #   GEN-INT-04: 11 failures/yr                → 1-2 this week
    #   Others: 2-8 failures/yr                   → 0-1 this week

    historical_faults = [
        # (day_offset, machine_id, fault_time_hr, duration_hrs, fault_code, fault_msg, category)
        (-7,  "PPU-FAB-03", 9.5,  3.2, "E-4409", "Plasma RF power transient — recovered after restart",           "Equipment Fault"),
        (-7,  "DLK-ASM-06", 14.0, 1.8, "E-7698", "PCIe link degraded — retimer FW cache flushed, restored",       "Equipment Fault"),
        (-6,  "PPU-FAB-03", 8.0,  4.5, "E-4410", "Plasma chamber pressure spike — vent cycle required",           "Equipment Fault"),
        (-6,  "GEN-INT-04", 11.5, 2.1, "E-9201", "JTAG bus contention — test socket 2 cleaned and restored",      "Equipment Fault"),
        (-5,  "PPU-FAB-02", 13.0, 1.6, "W-0822", "Etch rate 8% below target — gas flow regulator adjusted",       "Performance"),
        (-5,  "PPU-FAB-03", 7.0,  5.0, "E-4411", "RF matching network fault — capacitor replaced",                "Equipment Fault"),
        (-4,  "DLK-ASM-05", 10.0, 0.8, "W-5508", "Thermal ramp overshoot +2.1°C — PID tuned",                    "Quality Risk"),
        (-4,  "DLK-ASM-06", 9.0,  2.4, "E-7699", "NVMe PCIe Gen4 retrain — link degraded after power cycle",     "Equipment Fault"),
        (-4,  "PPU-FAB-03", 15.0, 3.8, "E-4412", "Plasma ignition failure — RF PSU partial fault",                "Equipment Fault"),
        (-3,  "GEN-INT-03", 12.0, 1.2, "W-3301", "Model flash speed 15% below spec — socket contention",         "Performance"),
        (-3,  "PPU-FAB-04", 8.5,  2.0, "W-1801", "CVD precursor flow drop 12% — MFC recalibrated",               "Equipment Fault"),
        (-2,  "PPU-FAB-03", 10.0, 4.1, "E-4412", "Plasma ignition failure — recurring RF PSU degradation",       "Equipment Fault"),
        (-2,  "DLK-ASM-01", 14.5, 0.9, "W-0601", "SMT nozzle pressure low — feeder #12 cleaned",                 "Equipment Fault"),
        (-1,  "PPU-FAB-05", 9.0,  1.5, "W-1104", "Bond pull strength Cpk 1.41 — load cell drift detected",       "Quality Risk"),
        (-1,  "GEN-INT-04", 11.0, 2.7, "E-9202", "JTAG scan chain incomplete — bus isolation test run",          "Equipment Fault"),
        (-1,  "PPU-FAB-03", 8.0,  3.9, "E-4412", "Plasma ignition failure — 3rd occurrence this week",           "Equipment Fault"),
        (-1,  "DLK-ASM-06", 13.5, 1.5, "E-7700", "PCIe Gen5 link intermittent — retimer reconfigured",           "Equipment Fault"),
    ]

    event_rows = []
    ingest_ts = ingest_now()

    for (day_offset, machine_id, fault_hr, duration_hrs, code, msg, category) in historical_faults:
        day = TODAY + timedelta(days=day_offset)
        fault_ts   = day.replace(hour=0) + timedelta(hours=fault_hr)
        recover_ts = fault_ts + timedelta(hours=duration_hrs)
        severity   = "CRITICAL" if code.startswith("E-") else "HIGH"

        # Fault event
        event_rows.append(Row(
            event_id=uid(), machine_id=machine_id, event_ts=fault_ts,
            state="fault", fault_code=code, fault_msg=msg,
            idle_reason=None, maintenance_type=None,
            operator_id="OP-HIST", ingest_ts=ingest_ts
        ))
        # Recovery event
        event_rows.append(Row(
            event_id=uid(), machine_id=machine_id, event_ts=recover_ts,
            state="running", fault_code=None, fault_msg=None,
            idle_reason=None, maintenance_type=None,
            operator_id="OP-HIST", ingest_ts=ingest_ts
        ))

    spark.createDataFrame(event_rows).write.mode("append").saveAsTable("demo_nah_catalog.mfg_bronze.production_events_raw")
    print(f"  Production events: {len(event_rows)} historical fault/recovery pairs")

    # ── Historical alarms (all acknowledged and resolved) ─────────────────────
    alarm_rows = []
    for (day_offset, machine_id, fault_hr, duration_hrs, code, msg, category) in historical_faults:
        day = TODAY + timedelta(days=day_offset)
        triggered_ts = day.replace(hour=0) + timedelta(hours=fault_hr)
        ack_ts       = triggered_ts + timedelta(minutes=random.randint(5, 25))
        severity     = "CRITICAL" if code.startswith("E-") else "HIGH"
        alarm_rows.append(Row(
            alarm_id=uid(), machine_id=machine_id, severity=severity,
            code=code, message=msg, category=category,
            triggered_ts=triggered_ts, acknowledged=True,
            ack_ts=ack_ts, ack_by="OP-HIST",
            impact=f"Production impact: {random.choice(['Minor slowdown','Line capacity reduced 50%','Throughput loss ~20%'])}",
            ingest_ts=ingest_ts
        ))

    spark.createDataFrame(alarm_rows).write.mode("append").saveAsTable("demo_nah_catalog.mfg_bronze.alarm_events_raw")
    print(f"  Alarm events: {len(alarm_rows)} historical (all acknowledged)")

    # ── Historical quality inspections ────────────────────────────────────────
    # ~200 sampled inspections per shift × 14 shifts = ~2800 rows
    # Pass rate targets: PPU ~97%, DLA ~96.5%, GAM ~95%
    DEFECT_POOL = {
        "A": ["Bond Wire Short", "Contamination", "Misalignment", None, None, None, None, None, None],
        "B": ["Solder Bridge", "Missing Component", "Misalignment", None, None, None, None, None, None],
        "C": ["Misalignment", "Bond Wire Short", "Other",          None, None, None, None, None, None],
    }
    inspection_rows = []
    for (day_offset, period) in [(-7,"D"),(-7,"N"),(-6,"D"),(-6,"N"),(-5,"D"),(-5,"N"),
                                  (-4,"D"),(-4,"N"),(-3,"D"),(-3,"N"),(-2,"D"),(-2,"N"),(-1,"D"),(-1,"N")]:
        day = TODAY + timedelta(days=day_offset)
        shift_start = day.replace(hour=6) if period == "D" else day.replace(hour=18)
        shift_id    = f"{day.strftime('%Y-%m-%d')}-{period}"

        for m in MACHINES:
            # ~12 inspections per machine per shift
            for _ in range(12):
                offset_mins  = random.randint(0, 700)
                ts           = shift_start + timedelta(minutes=offset_mins)
                defect_pool  = DEFECT_POOL[m["line"]]
                defect       = random.choice(defect_pool)
                result       = "pass" if defect is None else random.choice(["fail", "rework"])
                inspection_rows.append(Row(
                    inspection_id=uid(),
                    unit_serial=f"{m['product']}-{day.strftime('%m%d')}-{random.randint(10000,99999)}",
                    machine_id=m["id"], line=m["line"], product=m["product"],
                    inspection_ts=ts, result=result, defect_type=defect,
                    shift_id=shift_id, ingest_ts=ingest_ts
                ))

    spark.createDataFrame(inspection_rows).write.mode("append").saveAsTable("demo_nah_catalog.mfg_bronze.quality_inspections_raw")
    print(f"  Quality inspections: {len(inspection_rows)} historical samples")

    print("  Chapter 1 complete — run silver + gold pipelines to see the 7-day baseline.")

# ══════════════════════════════════════════════════════════════════════════════
# CHAPTER 2 — TODAY'S SHIFT STARTS CLEAN (06:00–07:15)
# ──────────────────────────────────────────────────────────────────────────────
# Story: 6 AM. New crew arrives. All 18 machines initialize and come online.
# Plant OEE launches at 87.2% — tracking above the 88% daily target.
# Operators report nominal conditions across all three lines.
# The gold layer will show 18/18 machines running, no alarms.
# ══════════════════════════════════════════════════════════════════════════════

if CHAPTER >= 2:
    print("\n─── CHAPTER 2: Today's shift starts — all machines online ───")

    shift_id = f"{TODAY.strftime('%Y-%m-%d')}-D"
    ingest_ts = ingest_now()

    # Today's open shift record
    spark.createDataFrame([Row(
        shift_id=shift_id, line="ALL", product=None,
        start_ts=SHIFT_START, end_ts=None,  # open shift
        supervisor_id="OP-105", target_units=4200,
        ingest_ts=ingest_ts
    )]).write.mode("append").saveAsTable("demo_nah_catalog.mfg_bronze.shift_records_raw")

    # All 18 machines go from cold start → running at 06:00
    startup_events = []
    for m in MACHINES:
        startup_events.append(Row(
            event_id=uid(), machine_id=m["id"],
            event_ts=SHIFT_START,
            state="running", fault_code=None, fault_msg=None,
            idle_reason=None, maintenance_type=None,
            operator_id="OP-105", ingest_ts=ingest_ts
        ))
    spark.createDataFrame(startup_events).write.mode("append").saveAsTable("demo_nah_catalog.mfg_bronze.production_events_raw")

    # Telemetry 06:00–07:15 (all machines healthy, OEE climbing)
    telemetry_rows = []
    ts = SHIFT_START
    end = SHIFT_START + timedelta(hours=1, minutes=15)
    while ts <= end:
        for m in MACHINES:
            telemetry_rows.append(Row(
                machine_id=m["id"], ts=ts,
                oee_pct=oee_for(m, ts),
                temp_c=temp_for(m, ts),
                cycle_time_sec=cycle_for(m, ts),
                power_kw=round(m["base_oee"] * 0.08, 2),
                units_count=int(m["target_hr"] * ((ts - SHIFT_START).seconds / 3600)),
                ingest_ts=ingest_ts
            ))
        ts += timedelta(minutes=15)

    spark.createDataFrame(telemetry_rows).write.mode("append").saveAsTable("demo_nah_catalog.mfg_bronze.machine_telemetry_raw")
    print(f"  Startup events: {len(startup_events)} (all 18 machines → running)")
    print(f"  Telemetry: {len(telemetry_rows)} rows (06:00–07:15, all nominal)")
    print("  Chapter 2 complete — gold now shows 18/18 machines running, OEE ~87%.")

# ══════════════════════════════════════════════════════════════════════════════
# CHAPTER 3 — THE CRISIS UNFOLDS (07:30–12:45)
# ──────────────────────────────────────────────────────────────────────────────
# Story: Over six hours, five machines are taken offline by a cascade of faults.
#
# 07:30  PPU-FAB-03  E-4412  Plasma ignition failure (4th occurrence this week)
# 08:15  PPU-FAB-05          Bond wire quality failures begin appearing on Line A
# 09:00  PPU-FAB-06  W-1105  Wire bond calibration overdue → taken to maintenance
# 10:30  DLK-ASM-04  W-2201  NVMe flash station goes idle — firmware hold
# 11:00  DLK-ASM-05  W-5510  Thermal chamber excursion: 88.1°C vs 85°C setpoint
# 11:30  DLK-ASM-06  E-7701  PCIe Gen5 link training failure — 287 units queued
# 12:45  GEN-INT-04  E-9203  JTAG chain break — 94 GAMs pending verification
#
# Each fault drops a production_event + alarm_event at its precise timestamp.
# Telemetry shows OEE degrading on affected lines in real time.
# ══════════════════════════════════════════════════════════════════════════════

if CHAPTER >= 3:
    print("\n─── CHAPTER 3: Crisis unfolds — fault cascade ───")

    ingest_ts = ingest_now()
    event_rows  = []
    alarm_rows  = []

    def fault_at(h, m=0): return SHIFT_START + timedelta(hours=h, minutes=m)

    # ── 07:30 — PPU-FAB-03: Plasma Ignition Failure ───────────────────────────
    T_FAB03 = fault_at(1, 30)  # 1.5 hrs into shift
    event_rows.append(Row(
        event_id=uid(), machine_id="PPU-FAB-03", event_ts=T_FAB03,
        state="fault", fault_code="E-4412",
        fault_msg="Plasma Ignition Failure — RF power supply fault. Etching halted.",
        idle_reason=None, maintenance_type=None,
        operator_id="OP-201", ingest_ts=ingest_ts
    ))
    alarm_rows.append(Row(
        alarm_id="ALM-001", machine_id="PPU-FAB-03", severity="CRITICAL",
        code="E-4412",
        message="Plasma Ignition Failure — RF power supply fault. Etch line halted.",
        category="Equipment Fault", triggered_ts=T_FAB03,
        acknowledged=False, ack_ts=None, ack_by=None,
        impact="Line A PPU output reduced 50% — 290 units/hr loss",
        ingest_ts=ingest_ts
    ))
    print(f"  07:30  PPU-FAB-03 → FAULT  E-4412 (plasma ignition)")

    # ── 09:00 — PPU-FAB-06: Scheduled Maintenance ────────────────────────────
    T_FAB06 = fault_at(3, 0)   # 3 hrs into shift
    event_rows.append(Row(
        event_id=uid(), machine_id="PPU-FAB-06", event_ts=T_FAB06,
        state="maintenance", fault_code=None, fault_msg=None,
        idle_reason=None,
        maintenance_type="Scheduled PM — Bond force & temperature calibration. Due every 500 cycles.",
        operator_id="OP-202", ingest_ts=ingest_ts
    ))
    alarm_rows.append(Row(
        alarm_id="ALM-005", machine_id="PPU-FAB-06", severity="HIGH",
        code="W-1105",
        message="Wire bond calibration overdue — tolerance drift on bond force sensor.",
        category="Maintenance Due", triggered_ts=T_FAB06,
        acknowledged=True,
        ack_ts=T_FAB06 + timedelta(minutes=8), ack_by="OP-202",
        impact="Bond pull strength approaching lower control limit — scrap risk if not calibrated",
        ingest_ts=ingest_ts
    ))
    print(f"  09:00  PPU-FAB-06 → MAINTENANCE  W-1105 (wire bond cal overdue)")

    # ── 10:30 — DLK-ASM-04: Firmware Hold → Idle ────────────────────────────
    T_ASM04 = fault_at(4, 30)  # 4.5 hrs into shift
    event_rows.append(Row(
        event_id=uid(), machine_id="DLK-ASM-04", event_ts=T_ASM04,
        state="idle", fault_code=None, fault_msg=None,
        idle_reason="Waiting for firmware v4.2.1 — deployment in progress from Databricks Repos",
        maintenance_type=None,
        operator_id="OP-203", ingest_ts=ingest_ts
    ))
    alarm_rows.append(Row(
        alarm_id="ALM-004", machine_id="DLK-ASM-04", severity="HIGH",
        code="W-2201",
        message="Firmware v4.2.1 not yet deployed — flash station idle.",
        category="Material / Software", triggered_ts=T_ASM04,
        acknowledged=True,
        ack_ts=T_ASM04 + timedelta(minutes=12), ack_by="OP-203",
        impact="NVMe flash throughput halted — 368 units/hr capacity waiting",
        ingest_ts=ingest_ts
    ))
    print(f"  10:30  DLK-ASM-04 → IDLE  W-2201 (firmware hold)")

    # ── 11:00 — DLK-ASM-05: Thermal Excursion ───────────────────────────────
    T_ASM05_ALARM = fault_at(5, 0)  # 5 hrs into shift
    alarm_rows.append(Row(
        alarm_id="ALM-007", machine_id="DLK-ASM-05", severity="MEDIUM",
        code="W-5510",
        message="Thermal chamber upper limit excursion — 88.1°C vs. 85°C setpoint.",
        category="Quality Risk", triggered_ts=T_ASM05_ALARM,
        acknowledged=False, ack_ts=None, ack_by=None,
        impact="3 Delta Arrays in current lot may require re-inspection",
        ingest_ts=ingest_ts
    ))
    print(f"  11:00  DLK-ASM-05 → ALARM  W-5510 (thermal excursion, still running)")

    # ── 11:30 — DLK-ASM-06: PCIe Gen5 Failure → Fault ──────────────────────
    T_ASM06 = fault_at(5, 30)  # 5.5 hrs into shift
    event_rows.append(Row(
        event_id=uid(), machine_id="DLK-ASM-06", event_ts=T_ASM06,
        state="fault", fault_code="E-7701",
        fault_msg="NVMe Interface Error — PCIe Gen5 link training failure. 287 units queued.",
        idle_reason=None, maintenance_type=None,
        operator_id="OP-204", ingest_ts=ingest_ts
    ))
    alarm_rows.append(Row(
        alarm_id="ALM-002", machine_id="DLK-ASM-06", severity="CRITICAL",
        code="E-7701",
        message="NVMe PCIe Gen5 link training failure. Final test blocked.",
        category="Equipment Fault", triggered_ts=T_ASM06,
        acknowledged=False, ack_ts=None, ack_by=None,
        impact="287 Delta Arrays queued, 78 units/hr final test capacity lost",
        ingest_ts=ingest_ts
    ))
    print(f"  11:30  DLK-ASM-06 → FAULT  E-7701 (PCIe Gen5 link training failure)")

    # ── 12:45 — GEN-INT-04: JTAG Chain Break → Fault ────────────────────────
    T_INT04 = fault_at(6, 45)  # 6.75 hrs into shift
    event_rows.append(Row(
        event_id=uid(), machine_id="GEN-INT-04", event_ts=T_INT04,
        state="fault", fault_code="E-9203",
        fault_msg="JTAG Chain Break — boundary scan controller unreachable. 94 GAMs pending verification.",
        idle_reason=None, maintenance_type=None,
        operator_id="OP-205", ingest_ts=ingest_ts
    ))
    alarm_rows.append(Row(
        alarm_id="ALM-003", machine_id="GEN-INT-04", severity="CRITICAL",
        code="E-9203",
        message="JTAG boundary scan controller unreachable — chain break detected.",
        category="Equipment Fault", triggered_ts=T_INT04,
        acknowledged=True,
        ack_ts=T_INT04 + timedelta(minutes=7), ack_by="OP-205",
        impact="94 Genie AI Modules pending functional verification",
        ingest_ts=ingest_ts
    ))
    print(f"  12:45  GEN-INT-04 → FAULT  E-9203 (JTAG chain break)")

    # ── GEN-INT-03 performance alarm (ongoing degradation) ───────────────────
    T_INT03_ALARM = fault_at(1, 35)  # shortly after shift start
    alarm_rows.append(Row(
        alarm_id="ALM-006", machine_id="GEN-INT-03", severity="MEDIUM",
        code="W-3302",
        message="Model flash speed 22% below cycle time target.",
        category="Performance", triggered_ts=T_INT03_ALARM,
        acknowledged=True,
        ack_ts=T_INT03_ALARM + timedelta(minutes=15), ack_by="OP-201",
        impact="Genie AI Module flash rate 197/hr vs. 252/hr target",
        ingest_ts=ingest_ts
    ))

    spark.createDataFrame(event_rows).write.mode("append").saveAsTable("demo_nah_catalog.mfg_bronze.production_events_raw")
    spark.createDataFrame(alarm_rows).write.mode("append").saveAsTable("demo_nah_catalog.mfg_bronze.alarm_events_raw")

    # ── Quality defects on Line A starting at 08:15 ───────────────────────────
    # Bond wire shorts appear as PPU-FAB-03 goes down and PPU-FAB-05 absorbs load
    quality_rows = []
    shift_id = f"{TODAY.strftime('%Y-%m-%d')}-D"
    defect_wave_start = fault_at(2, 15)  # 08:15

    for m in MACHINES:
        fault_ts = {
            "PPU-FAB-03": T_FAB03,
            "PPU-FAB-06": T_FAB06,
            "DLK-ASM-04": T_ASM04,
            "DLK-ASM-06": T_ASM06,
            "GEN-INT-04": T_INT04,
        }.get(m["id"])

        # Generate inspections across this shift (06:00–13:00)
        for _ in range(18):  # ~18 samples per machine = ~4218 total shift (matches app)
            offset_mins = random.randint(0, 420)  # 7-hour window
            ts = SHIFT_START + timedelta(minutes=offset_mins)

            # Higher defect rate after 08:15 on Line A machines
            defect_elevated = (m["line"] == "A" and ts >= defect_wave_start)

            if fault_ts and ts >= fault_ts:
                result, defect = "pass", None  # faulted machines produce nothing
            elif m["line"] == "A" and defect_elevated:
                choices = ["Bond Wire Short", None, None, None, "Contamination", None, None]
                defect  = random.choice(choices)
                result  = "pass" if defect is None else random.choice(["fail","rework"])
            elif m["line"] == "B":
                choices = ["Solder Bridge", None, None, None, None, "Missing Component", None, None, None]
                defect  = random.choice(choices)
                result  = "pass" if defect is None else random.choice(["fail","rework"])
            elif m["line"] == "C":
                choices = ["Misalignment", None, None, None, None, None, "Other", None, None]
                defect  = random.choice(choices)
                result  = "pass" if defect is None else random.choice(["fail","rework"])
            else:
                result, defect = "pass", None

            quality_rows.append(Row(
                inspection_id=uid(),
                unit_serial=f"{m['product']}-{TODAY.strftime('%m%d')}-{random.randint(10000,99999)}",
                machine_id=m["id"], line=m["line"], product=m["product"],
                inspection_ts=ts, result=result, defect_type=defect,
                shift_id=shift_id, ingest_ts=ingest_ts
            ))

    spark.createDataFrame(quality_rows).write.mode("append").saveAsTable("demo_nah_catalog.mfg_bronze.quality_inspections_raw")

    print(f"\n  Crisis events:   {len(event_rows)} state transitions")
    print(f"  Active alarms:   {len(alarm_rows)} (3 CRITICAL, 2 HIGH, 2 MEDIUM)")
    print(f"  Quality samples: {len(quality_rows)} (this shift, elevated Line A defects)")
    print("  Chapter 3 complete — run silver + gold pipelines to see plant in crisis.")

# ══════════════════════════════════════════════════════════════════════════════
# CHAPTER 4 — CURRENT STATE SNAPSHOT (13:00)
# ──────────────────────────────────────────────────────────────────────────────
# Story: 13:00 — one hour after the last fault. The plant is operating with
# 13/18 machines running. OEE has dropped from 87.2% at shift start to 83.1%.
# Production shortfall: PPU -18%, DLA -22%, GAM -12% vs. target.
# SHIFT AI is now pointing engineers at the root causes. Recovery underway.
# ══════════════════════════════════════════════════════════════════════════════

if CHAPTER >= 4:
    print("\n─── CHAPTER 4: Live state snapshot — 13:00 ───")

    ingest_ts = ingest_now()
    snapshot_ts = SHIFT_START + timedelta(hours=7)  # 13:00

    # Define which machines are in what state right now
    current_states = {
        "PPU-FAB-03": "fault",
        "PPU-FAB-06": "maintenance",
        "DLK-ASM-04": "idle",
        "DLK-ASM-06": "fault",
        "GEN-INT-04": "fault",
    }  # all others: running

    # Final telemetry snapshot for all running machines
    telemetry_rows = []
    ts_from = SHIFT_START + timedelta(hours=1, minutes=30)  # pick up from 07:30
    ts_cursor = ts_from
    while ts_cursor <= snapshot_ts:
        for m in MACHINES:
            state = current_states.get(m["id"], "running")
            fault_time = {
                "PPU-FAB-03": SHIFT_START + timedelta(hours=1, minutes=30),
                "PPU-FAB-06": SHIFT_START + timedelta(hours=3),
                "DLK-ASM-04": SHIFT_START + timedelta(hours=4, minutes=30),
                "DLK-ASM-06": SHIFT_START + timedelta(hours=5, minutes=30),
                "GEN-INT-04": SHIFT_START + timedelta(hours=6, minutes=45),
            }.get(m["id"])

            is_active = (fault_time is None or ts_cursor < fault_time)
            oee = oee_for(m, ts_cursor, fault_at=fault_time) if is_active else 0.0

            telemetry_rows.append(Row(
                machine_id=m["id"], ts=ts_cursor,
                oee_pct=oee,
                temp_c=temp_for(m, ts_cursor),
                cycle_time_sec=cycle_for(m, ts_cursor) if is_active else m["cycle"],
                power_kw=round(m["base_oee"] * 0.08 * (1 if is_active else 0.1), 2),
                units_count=(
                    int(m["target_hr"] * ((ts_cursor - SHIFT_START).seconds / 3600))
                    if is_active else 0
                ),
                ingest_ts=ingest_ts
            ))
        ts_cursor += timedelta(minutes=15)

    spark.createDataFrame(telemetry_rows).write.mode("append").saveAsTable("demo_nah_catalog.mfg_bronze.machine_telemetry_raw")

    # Summary
    print(f"  Telemetry: {len(telemetry_rows)} rows (07:30–13:00, fault degradation visible)")
    print("\n  PLANT STATE AT 13:00:")
    print("  Running:     13/18  (PPU lines: 4, DLA lines: 3, GAM lines: 4)")
    print("  Fault:        3/18  (PPU-FAB-03, DLK-ASM-06, GEN-INT-04)")
    print("  Maintenance:  1/18  (PPU-FAB-06)")
    print("  Idle:         1/18  (DLK-ASM-04)")
    print("  Plant OEE:   ~83%   (was 87.2% at shift start)")
    print("\n  Chapter 4 complete — run silver + gold pipelines.")
    print("  The app will now read live data from demo_nah_catalog.mfg_gold.*")
