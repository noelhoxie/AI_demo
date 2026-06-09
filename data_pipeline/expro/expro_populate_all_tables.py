# Databricks notebook source
# MAGIC %md
# MAGIC # Expro Schema — Populate All Empty Tables
# MAGIC Populates every empty table in the `expro` schema with realistic operational data.
# MAGIC Data is consistent with existing rows in `expro_rigs`, `equipment_master`, and `well_master`.
# MAGIC
# MAGIC **Tables populated:**
# MAGIC - `alarm_history` — sensor/equipment alarms (links to equipment_master + well_master)
# MAGIC - `calibration_records` — instrument calibration history
# MAGIC - `daily_reports` — daily operational reports per rig
# MAGIC - `equipment_health` — time-series health snapshots
# MAGIC - `incidents` — HSE incidents
# MAGIC - `permits_to_work` — PTW records
# MAGIC - `personnel_on_board` — POB manifest
# MAGIC - `safety_observations` — safety observation cards
# MAGIC - `scada_readings` — SCADA tag readings (partitioned by reading_date)
# MAGIC - `shift_handovers` — shift handover records
# MAGIC - `spare_parts_inventory` — spare parts per rig
# MAGIC - `work_orders` — corrective/preventive work orders (links to equipment_master)

# COMMAND ----------

dbutils.widgets.text("catalog", "demo_nah_catalog", "Catalog")
dbutils.widgets.text("schema",  "expro",            "Schema")
catalog = (dbutils.widgets.get("catalog") or "demo_nah_catalog").strip()
schema  = (dbutils.widgets.get("schema")  or "expro").strip()
print(f"Target: {catalog}.{schema}")

# COMMAND ----------
# MAGIC %md ## Shared reference data

# COMMAND ----------

import random
from datetime import date, datetime, timedelta
from pyspark.sql import functions as F

random.seed(7474)

# ── Rig IDs (from expro_rigs — used by operational tables) ────────────────────
EX_RIGS = [
    ("EX-001","Expro Vanguard",    "FPSO",           "Gulf of Mexico"),
    ("EX-002","Expro Titan",       "Jack-up",        "North Sea"),
    ("EX-003","Expro Pioneer",     "Semi-sub",       "Middle East"),
    ("EX-004","Expro Ranger",      "Drillship",      "Gulf of Mexico"),
    ("EX-005","Expro Atlantic",    "FPSO",           "Gulf of Mexico"),
    ("EX-006","Expro Viking",      "Semi-sub",       "North Sea"),
    ("EX-007","Expro Norseman",    "Jack-up",        "North Sea"),
    ("EX-008","Expro Britannia",   "FPSO",           "North Sea"),
    ("EX-009","Expro Magnus",      "Fixed Platform", "North Sea"),
    ("EX-010","Expro Orion",       "Semi-sub",       "Middle East"),
    ("EX-011","Expro Falcon",      "Jack-up",        "Middle East"),
    ("EX-012","Expro Phoenix",     "FPSO",           "Middle East"),
    ("EX-013","Expro Arabia",      "Fixed Platform", "Middle East"),
    ("EX-014","Expro Caspian",     "Semi-sub",       "Middle East"),
    ("EX-015","Expro Malabo",      "FPSO",           "West Africa"),
    ("EX-016","Expro Bonny",       "Jack-up",        "West Africa"),
    ("EX-017","Expro Niger",       "Semi-sub",       "West Africa"),
    ("EX-018","Expro Natuna",      "FPSO",           "Southeast Asia"),
    ("EX-019","Expro Borneo",      "Jack-up",        "Southeast Asia"),
    ("EX-020","Expro Malay",       "Semi-sub",       "Southeast Asia"),
]
EX_RIG_IDS = [r[0] for r in EX_RIGS]

# ── Equipment + Well IDs (from equipment_master / well_master) ─────────────────
EQ_IDS = (
    [f"EQ-001-{i:03d}" for i in range(1, 16)] +
    [f"EQ-002-{i:03d}" for i in range(1, 16)]
)
EQ_RIG_MAP = {f"EQ-001-{i:03d}": "RIG-001" for i in range(1, 16)}
EQ_RIG_MAP.update({f"EQ-002-{i:03d}": "RIG-002" for i in range(1, 16)})

EQ_TYPE_MAP = {
    "EQ-001-001":"separator",     "EQ-001-002":"separator",     "EQ-001-003":"HPU",
    "EQ-001-004":"DAU",           "EQ-001-005":"DAU",           "EQ-001-006":"chemical_skid",
    "EQ-001-007":"meter",         "EQ-001-008":"meter",         "EQ-001-009":"orifice_plate",
    "EQ-001-010":"generator",     "EQ-001-011":"generator",     "EQ-001-012":"bop",
    "EQ-001-013":"pressure_transmitter","EQ-001-014":"pressure_transmitter","EQ-001-015":"flow_computer",
    "EQ-002-001":"separator",     "EQ-002-002":"separator",     "EQ-002-003":"HPU",
    "EQ-002-004":"DAU",           "EQ-002-005":"DAU",           "EQ-002-006":"chemical_skid",
    "EQ-002-007":"meter",         "EQ-002-008":"meter",         "EQ-002-009":"orifice_plate",
    "EQ-002-010":"generator",     "EQ-002-011":"generator",     "EQ-002-012":"bop",
    "EQ-002-013":"pressure_transmitter","EQ-002-014":"pressure_transmitter","EQ-002-015":"flow_computer",
}

WELL_IDS = [f"WELL-{i:03d}" for i in range(1, 13)]
WELL_RIG_MAP = {f"WELL-{i:03d}": "RIG-001" for i in range(1, 7)}
WELL_RIG_MAP.update({f"WELL-{i:03d}": "RIG-002" for i in range(7, 13)})

PERSONNEL = [
    "M. Al-Rashid", "J. Thornton",  "C. Okonkwo",  "P. Andersen",
    "R. MacLeod",   "S. Petrov",    "L. Santos",   "D. Kim",
    "A. Nwosu",     "H. Eriksen",   "T. Nakamura", "F. Osei",
    "B. Williams",  "K. Jensen",    "N. Patel",    "G. Bouchard",
    "E. Olawale",   "I. Svensson",  "C. Leblanc",  "M. Rodriguez",
]

TODAY = date.today()
NOW   = datetime.utcnow()

def ts(days_ago=0, hours_ago=0, jitter_h=0):
    """Return ISO timestamp string offset from now."""
    dt = NOW - timedelta(days=days_ago, hours=hours_ago)
    if jitter_h:
        dt += timedelta(hours=random.uniform(-jitter_h, jitter_h))
    return dt.strftime("%Y-%m-%dT%H:%M:%S")

def d(days_ago=0, days_ahead=0):
    """Return ISO date string."""
    return (TODAY - timedelta(days=days_ago) + timedelta(days=days_ahead)).isoformat()

print("Reference data ready")

# COMMAND ----------
# MAGIC %md ## 1. alarm_history

# COMMAND ----------

random.seed(1001)

ALARM_TYPES = [
    "High_Pressure","Low_Pressure","High_Temperature","Low_Flow","High_Flow",
    "H2S_Alert","Low_Level","High_Level","Equipment_Fault","Communication_Loss",
    "Overspeed","Low_Voltage","Seal_Failure","Vibration_High",
]
ALARM_SEV = ["CRITICAL","HIGH","HIGH","MEDIUM","MEDIUM","MEDIUM","LOW","LOW"]

alarms = []
for i in range(1, 301):
    eq_id   = random.choice(EQ_IDS)
    rig_id  = EQ_RIG_MAP[eq_id]
    well_id = random.choice([w for w, r in WELL_RIG_MAP.items() if r == rig_id])
    tag_id  = f"{rig_id}-{EQ_TYPE_MAP[eq_id][:3].upper()}-TAG-{i:04d}"
    a_type  = random.choice(ALARM_TYPES)
    sev     = random.choice(ALARM_SEV)
    act_ts  = ts(days_ago=random.randint(0, 90), hours_ago=random.randint(0, 23))
    ack_dt  = None
    clr_dt  = None
    ack_by  = None
    if random.random() > 0.15:   # 85% acknowledged
        ack_dt = (datetime.strptime(act_ts, "%Y-%m-%dT%H:%M:%S")
                  + timedelta(minutes=random.randint(5, 180))).strftime("%Y-%m-%dT%H:%M:%S")
        ack_by = random.choice(PERSONNEL)
    if ack_dt and random.random() > 0.25:  # 75% of acknowledged are cleared
        clr_dt = (datetime.strptime(ack_dt, "%Y-%m-%dT%H:%M:%S")
                  + timedelta(minutes=random.randint(10, 480))).strftime("%Y-%m-%dT%H:%M:%S")
    desc = f"{a_type.replace('_',' ')} detected on {EQ_TYPE_MAP[eq_id]} {eq_id}"
    alarms.append((f"ALM-{i:05d}", tag_id, well_id, eq_id, a_type, sev,
                   act_ts, ack_dt, clr_dt, ack_by, desc))

alarm_schema = """
    alarm_id        STRING,
    tag_id          STRING,
    well_id         STRING,
    equipment_id    STRING,
    alarm_type      STRING,
    severity        STRING,
    activated_ts    TIMESTAMP,
    acknowledged_ts TIMESTAMP,
    cleared_ts      TIMESTAMP,
    acknowledged_by STRING,
    description     STRING
"""

alarm_df = spark.createDataFrame(alarms, alarm_schema)
alarm_df.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.alarm_history")
print(f"alarm_history: {alarm_df.count()} rows")
display(alarm_df.limit(5))

# COMMAND ----------
# MAGIC %md ## 2. calibration_records

# COMMAND ----------

random.seed(2002)

CAL_TYPES   = ["Initial","Periodic","Post_Repair","Pre_Deployment","Annual"]
CAL_RESULTS = ["Pass","Pass","Pass","Pass_With_Adjustment","Fail"]

cals = []
for i in range(1, 201):
    eq_id   = random.choice(EQ_IDS)
    cal_dt  = d(days_ago=random.randint(0, 730))
    cal_type = random.choice(CAL_TYPES)
    result   = random.choice(CAL_RESULTS)
    uncert   = round(random.uniform(0.05, 2.5), 3)
    cal_by   = random.choice(PERSONNEL)
    # next due: 90-365 days after calibration
    next_due_days = 365 if cal_type == "Annual" else 90 if cal_type == "Periodic" else 180
    next_dt  = (date.fromisoformat(cal_dt) + timedelta(days=next_due_days + random.randint(-10, 10))).isoformat()
    cert_ref = f"CERT-{i:05d}-{cal_dt[:4]}"
    cals.append((f"CAL-{i:05d}", eq_id, cal_dt, cal_type, result,
                 uncert, cal_by, next_dt, cert_ref))

cal_schema = """
    cal_id          STRING,
    equipment_id    STRING,
    cal_date        DATE,
    cal_type        STRING,
    cal_result      STRING,
    uncertainty_pct DOUBLE,
    calibrated_by   STRING,
    next_due_date   DATE,
    certificate_ref STRING
"""

cal_df = spark.createDataFrame(cals, cal_schema)
cal_df.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.calibration_records")
print(f"calibration_records: {cal_df.count()} rows")
display(cal_df.limit(5))

# COMMAND ----------
# MAGIC %md ## 3. daily_reports

# COMMAND ----------

random.seed(3003)

NPDT_REASONS = [
    "Equipment maintenance","Weather delay","Supply vessel operations",
    "Crew change","Wireline operations","Well testing","Planned shutdown",
    "Regulatory inspection","N/A",
]
SUPERVISORS = [p for p in PERSONNEL if "." in p]

reports = []
rid = 1
for rig_id, rig_name, _, _ in EX_RIGS:
    for day_ago in range(90, 0, -1):
        report_date = d(days_ago=day_ago)
        npdt = round(random.uniform(0, 4), 1) if random.random() < 0.35 else 0.0
        npdt_reason = random.choice(NPDT_REASONS) if npdt > 0 else "N/A"
        oil    = round(random.uniform(800, 7500), 1)
        gas    = round(random.uniform(0.3, 5.0), 3)
        hse_ev = random.choices([0, 0, 0, 1, 2], weights=[60, 20, 10, 7, 3])[0]
        wells_t = random.randint(0, 3)
        summary = (f"Operations normal. {wells_t} well test(s) completed. "
                   f"Oil: {oil:,.0f} bbl, Gas: {gas:.2f} MMscfd. "
                   + (f"NPDT: {npdt}h — {npdt_reason}." if npdt > 0 else "No NPDT recorded."))
        reports.append((f"RPT-{rid:06d}", rig_id, report_date, summary,
                        npdt, npdt_reason, wells_t, oil, gas, hse_ev,
                        random.choice(SUPERVISORS)))
        rid += 1

rpt_schema = """
    report_id           STRING,
    rig_id              STRING,
    report_date         DATE,
    operational_summary STRING,
    npdt_hours          DOUBLE,
    npdt_reason         STRING,
    wells_tested        INT,
    oil_produced_bbl    DOUBLE,
    gas_produced_mmscf  DOUBLE,
    hse_events          INT,
    authored_by         STRING
"""

rpt_df = spark.createDataFrame(reports, rpt_schema)
rpt_df.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.daily_reports")
print(f"daily_reports: {rpt_df.count()} rows")
display(rpt_df.orderBy("report_date", ascending=False).limit(5))

# COMMAND ----------
# MAGIC %md ## 4. equipment_health

# COMMAND ----------

random.seed(4004)

FAULT_CODES = ["FC-001","FC-002","FC-003","FC-004","FC-005",None,None,None,None,None]
FAULT_DESCS = {
    "FC-001":"High bearing temperature",
    "FC-002":"Abnormal vibration signature",
    "FC-003":"Seal leak detected",
    "FC-004":"Pressure drop across filter",
    "FC-005":"Communication timeout",
}

health_rows = []
hid = 1
# One snapshot every 6 hours for the last 30 days per equipment
for eq_id in EQ_IDS:
    for h_offset in range(0, 30*24, 6):
        snap_ts = (NOW - timedelta(hours=h_offset)).strftime("%Y-%m-%dT%H:%M:%S")
        score   = round(max(40, min(100, 85 + random.gauss(0, 8))), 1)
        vib     = round(max(0.1, random.gauss(3.5, 2.0)), 2)
        temp    = round(random.uniform(160, 380), 1)
        press   = round(random.uniform(800, 4500), 0)
        runtime = round(random.uniform(500, 8760), 0)
        fault   = random.choice(FAULT_CODES) if score < 70 else None
        fault_d = FAULT_DESCS.get(fault) if fault else None
        health_rows.append((f"EH-{hid:07d}", eq_id, snap_ts,
                            score, vib, temp, press, runtime, fault, fault_d))
        hid += 1

eh_schema = """
    health_id                STRING,
    equipment_id             STRING,
    snapshot_ts              TIMESTAMP,
    overall_health_score     DOUBLE,
    vibration_mm_s           DOUBLE,
    operating_temp_degf      DOUBLE,
    operating_pressure_psi   DOUBLE,
    runtime_hours            DOUBLE,
    fault_code               STRING,
    fault_description        STRING
"""

eh_df = spark.createDataFrame(health_rows, eh_schema)
eh_df.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.equipment_health")
print(f"equipment_health: {eh_df.count()} rows")
display(eh_df.limit(5))

# COMMAND ----------
# MAGIC %md ## 5. incidents

# COMMAND ----------

random.seed(5005)

INC_TYPES   = ["Near_Miss","First_Aid","Property_Damage","Environmental","Dangerous_Occurrence"]
INC_SEV     = ["HIGH","MEDIUM","MEDIUM","LOW","LOW"]
LOCATIONS   = ["Drill Floor","Main Deck","Engine Room","Process Module","Living Quarters",
                "Crane Pedestal","Chemical Storage","Pump Room","Subsea Bay","Helideck"]
ROOT_CAUSES = ["Human_Factor","Equipment_Failure","Procedure_Not_Followed",
                "Environmental_Conditions","Design_Deficiency","Inadequate_Training"]
INC_STATUSES = ["Closed","Closed","Closed","Under_Review","Open"]

incidents = []
for i in range(1, 121):
    rig_id   = random.choice(EX_RIG_IDS)
    i_type   = random.choice(INC_TYPES)
    i_sev    = INC_SEV[INC_TYPES.index(i_type)] if random.random() > 0.3 else random.choice(["HIGH","MEDIUM","LOW"])
    inc_ts   = ts(days_ago=random.randint(0, 180), hours_ago=random.randint(0, 23))
    loc      = random.choice(LOCATIONS)
    involved = random.randint(0, 3)
    rc       = random.choice(ROOT_CAUSES)
    actions  = f"Root cause identified: {rc.replace('_',' ')}. Corrective measures implemented and communicated to crew."
    status   = random.choice(INC_STATUSES)
    desc     = f"{i_type.replace('_',' ')} reported at {loc}. {involved} person(s) involved."
    incidents.append((f"INC-{i:05d}", rig_id, inc_ts, i_type, i_sev, loc,
                      desc, involved, rc, actions, status))

inc_schema = """
    incident_id         STRING,
    rig_id              STRING,
    incident_ts         TIMESTAMP,
    incident_type       STRING,
    severity            STRING,
    location            STRING,
    description         STRING,
    persons_involved    INT,
    root_cause          STRING,
    corrective_actions  STRING,
    status              STRING
"""

inc_df = spark.createDataFrame(incidents, inc_schema)
inc_df.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.incidents")
print(f"incidents: {inc_df.count()} rows")
display(inc_df.limit(5))

# COMMAND ----------
# MAGIC %md ## 6. permits_to_work

# COMMAND ----------

random.seed(6006)

PTW_TYPES  = ["Hot_Work","Cold_Work","Confined_Space","Electrical_Isolation",
               "Lifting_Operations","Working_at_Height","Diving_Operations"]
PTW_STATUSES = ["Active","Expired","Closed","Closed","Closed","Cancelled"]
ISOLATIONS   = ["LOTO applied","Blinding complete","N/A","Permit board updated","Gas tested"]
WORK_DESCS   = [
    "Welding on process pipework","Valve replacement — cold work",
    "Manway entry — separator vessel","Electrical panel maintenance",
    "Crane lift — 12t load","Working at height — platform inspection",
    "Pump impeller replacement","BOP test function","Generator overhaul",
    "HP pipe flange replacement","Fire and gas detector calibration",
    "Chemical injection skid service","Compressor valve service",
]

ptws = []
for i in range(1, 251):
    rig_id   = random.choice(EX_RIG_IDS)
    p_type   = random.choice(PTW_TYPES)
    desc     = random.choice(WORK_DESCS)
    loc      = random.choice(LOCATIONS)
    issued_ts_str = ts(days_ago=random.randint(0, 30), hours_ago=random.randint(0, 23))
    issued_dt = datetime.strptime(issued_ts_str, "%Y-%m-%dT%H:%M:%S")
    validity_h = random.choice([8, 12, 24])
    expiry_dt  = issued_dt + timedelta(hours=validity_h)
    status     = random.choice(PTW_STATUSES)
    # Active only if expiry is in the future
    if expiry_dt < NOW:
        status = "Expired" if status == "Active" else status
    issued_by = random.choice(PERSONNEL)
    resp      = random.choice(PERSONNEL)
    isolation = random.choice(ISOLATIONS)
    ptws.append((f"PTW-{i:05d}", rig_id, desc, p_type, loc,
                 issued_ts_str, expiry_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                 status, issued_by, resp, isolation))

ptw_schema = """
    ptw_id               STRING,
    rig_id               STRING,
    work_description     STRING,
    ptw_type             STRING,
    location             STRING,
    issued_ts            TIMESTAMP,
    expiry_ts            TIMESTAMP,
    status               STRING,
    issued_by            STRING,
    responsible_person   STRING,
    isolations_required  STRING
"""

ptw_df = spark.createDataFrame(ptws, ptw_schema)
ptw_df.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.permits_to_work")
print(f"permits_to_work: {ptw_df.count()} rows")
display(ptw_df.limit(5))

# COMMAND ----------
# MAGIC %md ## 7. personnel_on_board

# COMMAND ----------

random.seed(7007)

COMPANIES   = ["Expro International","Halliburton","Schlumberger","Baker Hughes",
                "TechnipFMC","Subsea 7","Transocean","NOV","Parker Hannifin","ABB"]
ROLES       = ["OIM","Toolpusher","Driller","Assistant Driller","Subsea Engineer",
                "Production Technician","Electrician","Mechanic","Medic","Crane Operator",
                "Roustabout","Roughneck","Well Engineer","Safety Officer","Catering Manager"]
SIZES       = ["S","M","M","L","L","XL","XL","XXL"]
MUSTER_STAS = ["A","B","C","D"]
FIRST_NAMES = ["James","Sarah","Mohammed","Priya","Erik","Chidi","Yuki","Anna",
                "Carlos","Fatima","David","Ingrid","Wei","Olusegun","Marie"]
LAST_NAMES  = ["Smith","Johnson","Al-Khatib","Patel","Lindqvist","Okafor","Tanaka",
               "Johansson","Reyes","Hassan","Brown","Eriksson","Zhang","Adeyemi","Dubois"]

pobs = []
for i in range(1, 401):
    rig_id   = random.choice(EX_RIG_IDS)
    name     = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
    company  = random.choice(COMPANIES)
    role     = random.choice(ROLES)
    days_onb = random.randint(0, 14)
    embark   = ts(days_ago=days_onb, hours_ago=random.randint(0, 12))
    disemb_dt = (datetime.strptime(embark, "%Y-%m-%dT%H:%M:%S")
                 + timedelta(days=14 - days_onb + random.randint(0, 7)))
    size     = random.choice(SIZES)
    muster   = random.choice(MUSTER_STAS)
    ec_first = random.choice(FIRST_NAMES)
    ec_last  = random.choice(LAST_NAMES)
    ec       = f"{ec_first} {ec_last} +{random.randint(1,99):02d}{random.randint(100,999)}{random.randint(1000000,9999999)}"
    pobs.append((f"POB-{i:05d}", rig_id, name, company, role,
                 embark, disemb_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                 size, muster, ec))

pob_schema = """
    pob_id                    STRING,
    rig_id                    STRING,
    person_name               STRING,
    company                   STRING,
    role                      STRING,
    embark_ts                 TIMESTAMP,
    scheduled_disembark_ts    TIMESTAMP,
    survival_suit_size        STRING,
    muster_station            STRING,
    emergency_contact         STRING
"""

pob_df = spark.createDataFrame(pobs, pob_schema)
pob_df.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.personnel_on_board")
print(f"personnel_on_board: {pob_df.count()} rows")
display(pob_df.limit(5))

# COMMAND ----------
# MAGIC %md ## 8. safety_observations

# COMMAND ----------

random.seed(8008)

OBS_TYPES  = ["Positive","Unsafe_Act","Unsafe_Condition","Near_Miss","Good_Practice"]
OBS_SEV    = ["LOW","LOW","MEDIUM","MEDIUM","HIGH"]
OBS_STATUS = ["Closed","Closed","In_Progress","Open"]
OBS_DESCS  = [
    "Housekeeping on main deck — good practice observed.",
    "PPE not worn in designated area.",
    "Spill on grating near pump — slip hazard.",
    "Hand near pinch point during valve operation.",
    "Positive observation: correct use of 3-point contact on ladder.",
    "Loose fitting not properly tightened.",
    "Fire extinguisher access blocked by equipment.",
    "Toolbox talk conducted effectively by crew.",
    "Barricading not erected around open grating.",
    "Correct task risk assessment completed before job start.",
]

obs_list = []
for i in range(1, 301):
    rig_id   = random.choice(EX_RIG_IDS)
    obs_ts   = ts(days_ago=random.randint(0, 60), hours_ago=random.randint(0, 23))
    o_type   = random.choice(OBS_TYPES)
    idx      = OBS_TYPES.index(o_type)
    sev      = OBS_SEV[idx]
    loc      = random.choice(LOCATIONS)
    desc     = random.choice(OBS_DESCS)
    sub_by   = random.choice(PERSONNEL)
    status   = random.choice(OBS_STATUS)
    ca       = ("No action required." if o_type in ("Positive","Good_Practice")
                else f"Corrective action raised: {desc.split('.')[0]}. Supervisor notified.")
    obs_list.append((f"OBS-{i:05d}", rig_id, obs_ts, o_type, sev, loc,
                     desc, sub_by, status, ca))

obs_schema = """
    obs_id            STRING,
    rig_id            STRING,
    obs_ts            TIMESTAMP,
    obs_type          STRING,
    severity          STRING,
    location          STRING,
    description       STRING,
    submitted_by      STRING,
    status            STRING,
    corrective_action STRING
"""

obs_df = spark.createDataFrame(obs_list, obs_schema)
obs_df.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.safety_observations")
print(f"safety_observations: {obs_df.count()} rows")
display(obs_df.limit(5))

# COMMAND ----------
# MAGIC %md ## 9. scada_readings (partitioned by reading_date)

# COMMAND ----------

random.seed(9009)

# Tag definitions per equipment type
TAG_DEFS = {
    "separator":           [("PT","psi",500,4500),("TT","degF",150,350),("FT","bbl/d",100,5000),("LT","pct",10,90)],
    "HPU":                 [("PT","psi",1500,5000),("TT","degF",120,250),("FT","gal/min",10,80)],
    "DAU":                 [("VT","V",110,125),("AT","A",5,50)],
    "chemical_skid":       [("FT","L/hr",5,200),("LT","pct",20,80)],
    "meter":               [("FT","MMscfd",0.1,5.0),("PT","psi",100,2000)],
    "orifice_plate":       [("FT","bbl/d",50,3000),("PT","psi",100,1000)],
    "generator":           [("PT","kW",100,2000),("TT","degF",150,300),("VT","V",440,480)],
    "bop":                 [("PT","psi",2000,10000),("TT","degF",60,250),("FT","gal/min",0,50)],
    "pressure_transmitter":[("PT","psi",200,5000)],
    "flow_computer":       [("FT","MMscfd",0.01,10.0)],
}

scada = []
rid_s = 1
# 7 days of hourly readings per equipment tag
for eq_id in EQ_IDS:
    rig_id  = EQ_RIG_MAP[eq_id]
    eq_type = EQ_TYPE_MAP[eq_id]
    tags    = TAG_DEFS.get(eq_type, [("PT","psi",100,5000)])
    well_id = random.choice([w for w, r in WELL_RIG_MAP.items() if r == rig_id])
    for tag_prefix, unit, lo, hi in tags:
        tag_id = f"{rig_id}-{eq_id[-3:]}-{tag_prefix}-{rid_s:04d}"
        base   = random.uniform(lo*0.6+hi*0.4, lo*0.3+hi*0.7)
        for h in range(7 * 24):
            read_ts  = (NOW - timedelta(hours=7*24-h)).strftime("%Y-%m-%dT%H:%M:%S")
            read_dt  = (NOW - timedelta(hours=7*24-h)).date().isoformat()
            val      = round(max(lo*0.8, min(hi*1.1, base + random.gauss(0, (hi-lo)*0.03))), 3)
            quality  = random.choices(["GOOD","BAD","UNCERTAIN"], weights=[92, 3, 5])[0]
            scada.append((f"RDG-{rid_s:07d}", tag_id, well_id, eq_id,
                          read_ts, val, unit, quality, rig_id, read_dt))
            rid_s += 1

scada_schema = """
    reading_id    STRING,
    tag_id        STRING,
    well_id       STRING,
    equipment_id  STRING,
    reading_ts    TIMESTAMP,
    value         DOUBLE,
    unit          STRING,
    quality_flag  STRING,
    rig_id        STRING,
    reading_date  DATE
"""

scada_df = spark.createDataFrame(scada, scada_schema)
(scada_df.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema","true")
    .partitionBy("reading_date")
    .saveAsTable(f"`{catalog}`.`{schema}`.scada_readings"))
print(f"scada_readings: {scada_df.count()} rows")
display(scada_df.limit(5))

# COMMAND ----------
# MAGIC %md ## 10. shift_handovers

# COMMAND ----------

random.seed(1010)

OPEN_ITEMS_POOL = [
    "BOP function test due — scheduled 06:00 tomorrow.",
    "Mud pump #2 liner change in progress — expected completion next shift.",
    "P1 WO on generator G-02 — parts on order ETA 48h.",
    "Gas compressor high vibration alarm — monitoring at 30-min intervals.",
    "ROV operations pending weather window.",
    "Well test on WELL-007 ongoing — data logger active.",
    "Chemical injection rate increased per engineer's instruction.",
    "Crane 2 inspection due — deferred pending offshore crane technician.",
]
SAFETY_NOTES_POOL = [
    "No safety incidents this shift. STOP card completed by all personnel.",
    "PTW hot work expired — renewed for next shift. Crew briefed.",
    "H2S detector bump-tested and calibrated. All units functional.",
    "Toolbox talk: dropped objects awareness. Attended by full crew.",
    "Fire drill completed 14:00. Muster time 3 min 12 sec.",
]
EQ_NOTES_POOL = [
    "All equipment running normally.",
    "Mud pump #1 pressure fluctuation — monitoring.",
    "Generator G-01 load balanced. G-02 on standby.",
    "Separator vessel level control auto mode confirmed.",
    "HPU oil level checked and topped up.",
]
WELL_NOTES_POOL = [
    "All wells on production. Choke settings unchanged.",
    "WELL-003 choke adjusted 20/64 to 22/64 per engineer instruction.",
    "WELL-007 shut-in for well test — reopening next shift.",
    "No well interventions this shift.",
    "Gas lift rate increased on WELL-004.",
]

handovers = []
for i in range(1, 361):
    rig_id   = random.choice(EX_RIG_IDS)
    days_ago = random.randint(0, 90)
    shift    = random.choice(["Day","Night"])
    h_ts     = ts(days_ago=days_ago, hours_ago=0 if shift == "Day" else 12)
    out_sup  = random.choice(PERSONNEL)
    in_sup   = random.choice([p for p in PERSONNEL if p != out_sup])
    open_i   = random.choice(OPEN_ITEMS_POOL)
    saf_n    = random.choice(SAFETY_NOTES_POOL)
    eq_n     = random.choice(EQ_NOTES_POOL)
    well_n   = random.choice(WELL_NOTES_POOL)
    handovers.append((f"SHO-{i:06d}", rig_id, h_ts, shift,
                      out_sup, in_sup, open_i, saf_n, eq_n, well_n))

sho_schema = """
    handover_id          STRING,
    rig_id               STRING,
    handover_ts          TIMESTAMP,
    shift                STRING,
    outgoing_supervisor  STRING,
    incoming_supervisor  STRING,
    open_items           STRING,
    safety_notes         STRING,
    equipment_notes      STRING,
    well_notes           STRING
"""

sho_df = spark.createDataFrame(handovers, sho_schema)
sho_df.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.shift_handovers")
print(f"shift_handovers: {sho_df.count()} rows")
display(sho_df.limit(5))

# COMMAND ----------
# MAGIC %md ## 11. spare_parts_inventory

# COMMAND ----------

random.seed(1111)

PARTS_CATALOG = [
    ("Mud pump liner set",           "Mud Pump",        "set",    2, 4,  6),
    ("BOP ram seal assembly",        "BOP Stack",       "set",    2, 4,  6),
    ("Centrifugal pump impeller",    "Centrifugal Pump","ea",     1, 2,  3),
    ("Generator AVR module",         "Generator",       "ea",     1, 2,  3),
    ("Gas compressor valve kit",     "Gas Compressor",  "kit",    2, 3,  5),
    ("Drawworks brake lining",       "Drawworks",       "set",    1, 2,  3),
    ("Top drive gearbox oil seal",   "Top Drive",       "set",    2, 4,  6),
    ("SCR cooling fan 24V",          "SCR Panel",       "ea",     2, 4,  6),
    ("Riser slip ring assembly",     "Riser System",    "ea",     1, 2,  3),
    ("Wellhead BX ring gasket",      "Wellhead Assembly","ea",    4, 8, 12),
    ("High pressure hose 1in x 5m",  "Hydraulics",      "m",      5,10, 15),
    ("Filter element 10 micron",     "Hydraulics",      "ea",     4, 8, 12),
    ("Hydraulic cylinder seal kit",  "Hydraulics",      "kit",    2, 4,  6),
    ("H2S detector sensor cell",     "Safety",          "ea",     4, 6,  8),
    ("SCBA cylinder 30 min",         "Safety",          "ea",     6,10, 15),
    ("Cable gland Pg21 ATEX",        "Electrical",      "ea",     6,12, 20),
    ("Motor start capacitor",        "Electrical",      "ea",     2, 4,  6),
    ("Stainless stud bolt 3/4in",    "Fasteners",       "ea",    20,40, 60),
    ("Bearing SKF 6305-2RS",         "Rotating Equipment","ea",   2, 4,  6),
    ("Shaft coupling insert",        "Rotating Equipment","ea",   2, 4,  6),
]
STORAGE_LOCS = ["A-Deck Store","B-Deck Store","Engine Room Store",
                 "Chemical Store","Main Deck Store","Drill Floor Store"]

parts = []
pid = 1
for rig_id, _, _, _ in EX_RIGS:
    for part_name, eq_type, unit, min_q, reorder_p, max_q in PARTS_CATALOG:
        qty = random.randint(0, max_q + 5)
        loc = random.choice(STORAGE_LOCS)
        updated = ts(days_ago=random.randint(0, 30))
        parts.append((f"PRT-{pid:05d}", rig_id, part_name, eq_type,
                       qty, min_q, reorder_p, unit, loc, updated))
        pid += 1

sp_schema = """
    part_id        STRING,
    rig_id         STRING,
    part_name      STRING,
    equipment_type STRING,
    qty_on_hand    INT,
    min_qty        INT,
    reorder_point  INT,
    unit           STRING,
    location       STRING,
    last_updated   TIMESTAMP
"""

sp_df = spark.createDataFrame(parts, sp_schema)
sp_df.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.spare_parts_inventory")
print(f"spare_parts_inventory: {sp_df.count()} rows")
display(sp_df.orderBy(F.col("qty_on_hand") < F.col("min_qty"), ascending=False).limit(10))

# COMMAND ----------
# MAGIC %md ## 12. work_orders (links to equipment_master)

# COMMAND ----------

random.seed(1212)

WO_TYPES     = ["Corrective","Preventive","Inspection","Modification"]
WO_STATUSES  = ["Open","In_Progress","Completed","Completed","Completed","Cancelled"]
WO_PRIORITIES= ["HIGH","MEDIUM","MEDIUM","LOW"]
WO_DESCS     = [
    "Replace worn impeller — pump performance degraded.",
    "Annual preventive maintenance per OEM schedule.",
    "Pressure relief valve calibration and test.",
    "Seal replacement — oil ingress observed.",
    "Bearing inspection — high temperature alarm.",
    "Electrical panel thermographic inspection.",
    "Flow meter verification against fiscal meter.",
    "BOP hydraulic test — regulatory requirement.",
    "Generator load bank test — standby unit.",
    "Chemical injection pump rate calibration.",
    "Instrumentation loop check — new well tie-in.",
    "Separator internal inspection — planned shutdown.",
]
DELAY_REASONS = [None,None,None,"Parts not in stock","Waiting for weather window",
                  "Crane not available","Permit delay","Specialist contractor required"]

wo_rows = []
wo_num  = 1
for i in range(1, 301):
    eq_id     = random.choice(EQ_IDS)
    wo_type   = random.choice(WO_TYPES)
    priority  = random.choice(WO_PRIORITIES)
    status    = random.choice(WO_STATUSES)
    created   = ts(days_ago=random.randint(1, 60))
    created_dt = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S")
    due_dt    = (created_dt + timedelta(days=random.randint(1, 30))).isoformat()
    comp_ts   = None
    if status == "Completed":
        comp_dt_obj = created_dt + timedelta(days=random.randint(1, 25))
        if comp_dt_obj < NOW:
            comp_ts = comp_dt_obj.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            status = "In_Progress"
    assigned  = random.choice(PERSONNEL)
    desc      = random.choice(WO_DESCS)
    delay     = random.choice(DELAY_REASONS) if status in ("Open","In_Progress") else None
    wo_rows.append((f"WO-{wo_num:06d}", eq_id, wo_type, priority, status,
                    created, due_dt, comp_ts, assigned, desc, delay))
    wo_num += 1

wo_schema = """
    wo_id          STRING,
    equipment_id   STRING,
    wo_type        STRING,
    priority       STRING,
    status         STRING,
    created_ts     TIMESTAMP,
    due_date       DATE,
    completed_ts   TIMESTAMP,
    assigned_to    STRING,
    description    STRING,
    delay_reason   STRING
"""

wo_df = spark.createDataFrame(wo_rows, wo_schema)
wo_df.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"`{catalog}`.`{schema}`.work_orders")
print(f"work_orders: {wo_df.count()} rows")
display(wo_df.orderBy("due_date").limit(10))

# COMMAND ----------
# MAGIC %md ## Final row count summary

# COMMAND ----------

tables = [
    "alarm_history","calibration_records","daily_reports","equipment_health",
    "incidents","permits_to_work","personnel_on_board","safety_observations",
    "scada_readings","shift_handovers","spare_parts_inventory","work_orders",
    # already populated
    "expro_rigs","expro_equipment","expro_anomalies","expro_work_orders",
    "equipment_master","well_master","well_integrity","well_tests",
]

print(f"\n{'Table':<35} {'Rows':>8}")
print("-" * 44)
for tbl in tables:
    try:
        n = spark.table(f"`{catalog}`.`{schema}`.{tbl}").count()
        print(f"{tbl:<35} {n:>8,}")
    except Exception as e:
        print(f"{tbl:<35}  ERROR: {e}")
print("\nAll tables populated.")
