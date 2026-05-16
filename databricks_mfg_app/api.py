"""
Databricks Manufacturing Intelligence Platform
Automotive shop floor monitoring — Body Shop · Paint Shop · Powertrain · Final Assembly
Products: Vehicle Body Assemblies (VBA) | Painted Body Units (PBU) | Powertrain Modules (PTM)
Shared convergence: Final Assembly Line (FAL-ASM-01) receives output from all 3 upstream lines
"""

import hashlib
import math
import os
import time
import requests
from functools import wraps
from flask import Flask, jsonify, request, send_from_directory, session, redirect

try:
    import psycopg2
    import psycopg2.extras
    _PSYCOPG2_OK = True
except ImportError:
    _PSYCOPG2_OK = False

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = os.getenv("SECRET_KEY", os.urandom(32))

# ── Auth ────────────────────────────────────────────────────────────────────────
COMPANY_NAME    = os.getenv("COMPANY_NAME", "")

@app.before_request
def _auto_auth_from_databricks():
    """When running as a Databricks App the platform forwards the user identity.
    Use it to silently authenticate the session so users never see the login form."""
    if session.get("authenticated"):
        return
    fwd_user = (request.headers.get("X-Forwarded-User")
                or request.headers.get("X-Forwarded-Email", ""))
    if fwd_user:
        session["authenticated"] = True
        session["username"]       = fwd_user
        session["company_name"]   = session.get("company_name") or COMPANY_NAME or "Databricks"

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "not authenticated"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

# ── Credentials ────────────────────────────────────────────────────────────────

def _creds():
    host  = os.environ["DATABRICKS_HOST"].rstrip("/")
    token = os.environ["DATABRICKS_TOKEN"]
    hdrs  = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return host, hdrs

GENIE_SPACE_ID          = os.getenv("GENIE_SPACE_ID", "")
LLM_ENDPOINT            = os.getenv("LLM_ENDPOINT", "databricks-meta-llama-3-3-70b-instruct")
SQL_WAREHOUSE_HTTP_PATH = os.getenv("SQL_WAREHOUSE_HTTP_PATH", "")  # e.g. /sql/1.0/warehouses/abc123

# Unity Catalog Vision
UC_CATALOG             = os.getenv("UC_CATALOG",  "demo_nah_catalog")
UC_SCHEMA              = os.getenv("UC_SCHEMA",   "mfg_vision")
UC_VOLUME              = os.getenv("UC_VOLUME",   "inspection_images")
VISION_MODEL_ENDPOINT  = os.getenv("VISION_MODEL_ENDPOINT", "")  # e.g. databricks-ecoat-defect-v2
PDM_ENDPOINT           = os.getenv("PDM_ENDPOINT", "predictive-maintenance")
MANUALS_ENDPOINT       = os.getenv("MANUALS_ENDPOINT", "mfg-manuals-rag")

# ── Lakebase (shared Databricks-managed PostgreSQL) ────────────────────────────
APP_NAME          = "Manufacturing Intelligence"
LAKEBASE_HOST     = os.getenv("LAKEBASE_HOST", "ep-old-boat-d835d01n.database.us-east-2.cloud.databricks.com")
LAKEBASE_PORT     = int(os.getenv("LAKEBASE_PORT", "5432"))
LAKEBASE_DB       = os.getenv("LAKEBASE_DB", "databricks_postgres")
LAKEBASE_USER     = os.getenv("LAKEBASE_USER", "")
LAKEBASE_ENDPOINT = os.getenv(
    "LAKEBASE_ENDPOINT",
    "projects/supply-chain-solution-studio/branches/production/endpoints/primary"
)
_LAKEBASE_OK = bool(LAKEBASE_HOST) and _PSYCOPG2_OK


def _lakebase_token():
    try:
        host = (os.getenv("LAKEBASE_DATABRICKS_HOST") or os.getenv("DATABRICKS_HOST", "")).rstrip("/")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        pat           = os.getenv("LAKEBASE_DATABRICKS_TOKEN") or os.getenv("DATABRICKS_TOKEN", "")
        client_id     = os.getenv("DATABRICKS_CLIENT_ID", "")
        client_secret = os.getenv("DATABRICKS_CLIENT_SECRET", "")
        if not host:
            return None
        if pat:
            bearer = pat
        elif client_id and client_secret:
            r = requests.post(
                f"{host}/oidc/v1/token",
                data={"grant_type": "client_credentials", "scope": "all-apis"},
                auth=(client_id, client_secret), timeout=10,
            )
            r.raise_for_status()
            bearer = r.json()["access_token"]
        else:
            return None
        r = requests.post(
            f"{host}/api/2.0/postgres/credentials",
            headers={"Authorization": f"Bearer {bearer}"},
            json={"endpoint": LAKEBASE_ENDPOINT}, timeout=10,
        )
        r.raise_for_status()
        return r.json().get("token")
    except Exception as e:
        print(f"[Lakebase] Token error: {e}", flush=True)
        return None


def _db_connect():
    tok = _lakebase_token()
    if not tok:
        raise RuntimeError("Could not obtain Lakebase token")
    return psycopg2.connect(
        host=LAKEBASE_HOST, port=LAKEBASE_PORT, dbname=LAKEBASE_DB,
        user=LAKEBASE_USER, password=tok, sslmode="require", connect_timeout=10,
    )


def _ensure_page_log_table():
    if not _LAKEBASE_OK:
        return
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS page_time_log (
                        id            SERIAL PRIMARY KEY,
                        username      TEXT,
                        page          TEXT,
                        seconds_spent INTEGER,
                        app_name      TEXT,
                        recorded_at   TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    ALTER TABLE page_time_log
                    ADD COLUMN IF NOT EXISTS app_name TEXT
                """)
            conn.commit()
        print(f"[Lakebase] page_time_log ready ({APP_NAME})", flush=True)
    except Exception as e:
        print(f"[Lakebase] Table setup error: {e}", flush=True)


_ensure_page_log_table()

# ── Gold table queries (when SQL_WAREHOUSE_HTTP_PATH is set) ───────────────────

def _query_gold(sql_text):
    """Execute SQL against a Databricks SQL Warehouse. Returns list of dicts, or None on error."""
    try:
        from databricks import sql as dbsql
        host  = os.environ["DATABRICKS_HOST"].replace("https://", "").rstrip("/")
        token = os.environ["DATABRICKS_TOKEN"]
        with dbsql.connect(
            server_hostname=host,
            http_path=SQL_WAREHOUSE_HTTP_PATH,
            access_token=token,
        ) as conn:
            with conn.cursor() as c:
                c.execute(sql_text)
                cols = [d[0] for d in c.description]
                return [dict(zip(cols, row)) for row in c.fetchall()]
    except Exception:
        return None


def _gold_machine_state():
    """Read current machine state from gold layer. Returns list of machine dicts."""
    rows = _query_gold("SELECT * FROM demo_nah_catalog.mfg_gold.machine_state ORDER BY line, machine_id")
    if not rows:
        return None
    return [
        {
            "id":               r["machine_id"],
            "line":             r["line"],
            "line_name":        r["line_name"],
            "name":             r["name"],
            "product":          r["product"],
            "state":            r["state"] or "running",
            "oee":              float(r["oee_pct"] or 0),
            "temp":             float(r["temp_c"] or 0),
            "cycle_time_sec":   float(r["cycle_time_sec"] or 0),
            "units_this_shift": int(r["units_this_shift"] or 0),
            "target_units_hr":  int(r["target_units_hr"] or 0),
            "fault_code":       r.get("fault_code"),
            "fault_msg":        r.get("fault_msg"),
            "idle_reason":      r.get("idle_reason"),
            "maintenance_type": r.get("maintenance_type"),
            "description":      r.get("description", ""),
        }
        for r in rows
    ]


def _gold_alarms():
    """Read active alarms from gold layer."""
    rows = _query_gold("""
        SELECT alarm_id, machine_id, severity, code, message, category,
               triggered_min_ago, acknowledged, impact
        FROM demo_nah_catalog.mfg_gold.alarms_active
        ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END,
                 triggered_min_ago
    """)
    if not rows:
        return None
    return [
        {
            "id":              r["alarm_id"],
            "machine_id":      r["machine_id"],
            "severity":        r["severity"],
            "code":            r["code"],
            "message":         r["message"],
            "category":        r["category"],
            "triggered_min_ago": int(r["triggered_min_ago"] or 0),
            "acknowledged":    bool(r["acknowledged"]),
            "impact":          r.get("impact", ""),
        }
        for r in rows
    ]


def _gold_oee_trend():
    """Read OEE trend from gold layer. Returns list matching OEE_TREND format."""
    rows = _query_gold("""
        SELECT shift_label, plant_oee, line_a_oee, line_b_oee, line_c_oee
        FROM demo_nah_catalog.mfg_gold.oee_by_shift
        ORDER BY shift_date ASC, shift_period ASC
        LIMIT 14
    """)
    if not rows:
        return None
    return [
        {
            "shift":  r["shift_label"],
            "plant":  float(r["plant_oee"] or 0),
            "line_a": float(r["line_a_oee"] or 0),
            "line_b": float(r["line_b_oee"] or 0),
            "line_c": float(r["line_c_oee"] or 0),
        }
        for r in rows
    ]


def _gold_downtime():
    """Read downtime pareto and MTBF from gold layer."""
    pareto = _query_gold("SELECT reason, minutes, pct FROM demo_nah_catalog.mfg_gold.downtime_pareto ORDER BY minutes DESC")
    mtbf   = _query_gold("SELECT machine_id, mtbf_hrs, mttr_hrs, failures_ytd, flagged FROM demo_nah_catalog.mfg_gold.mtbf_by_machine ORDER BY failures_ytd DESC")
    if not pareto or not mtbf:
        return None, None
    pareto_out = [{"reason": r["reason"], "minutes": int(r["minutes"] or 0), "pct": float(r["pct"] or 0)} for r in pareto]
    mtbf_out   = [{"id": r["machine_id"], "mtbf_hrs": float(r["mtbf_hrs"] or 0),
                   "mttr_hrs": float(r["mttr_hrs"] or 0), "failures_ytd": int(r["failures_ytd"] or 0),
                   "flagged": bool(r["flagged"])} for r in mtbf]
    return pareto_out, mtbf_out


def _gold_quality():
    """Read quality summary and defect types from gold layer."""
    summary = _query_gold("SELECT * FROM demo_nah_catalog.mfg_gold.quality_summary LIMIT 1")
    defects = _query_gold("SELECT defect_type, line, count, pct FROM demo_nah_catalog.mfg_gold.defects_by_type ORDER BY count DESC")
    if not summary or not defects:
        return None, None
    s = summary[0]
    summary_out = {
        "total_inspected_shift": int(s.get("total_inspected_shift") or 0),
        "total_passed_shift":    int(s.get("total_passed_shift") or 0),
        "total_scrap_shift":     int(s.get("total_scrap_shift") or 0),
        "total_rework_shift":    int(s.get("total_rework_shift") or 0),
        "first_pass_yield":      float(s.get("first_pass_yield") or 0),
        "scrap_rate_pct":        float(s.get("scrap_rate_pct") or 0),
        "rework_rate_pct":       float(s.get("rework_rate_pct") or 0),
        "target_fpy":            99.0,
    }
    defects_out = [{"type": r["defect_type"], "count": int(r["count"] or 0),
                    "line": r["line"], "pct": float(r["pct"] or 0)} for r in defects]
    return summary_out, defects_out


# ── Live simulation helpers ────────────────────────────────────────────────────

def _sin_val(base, amp, period, seed=0):
    """Sinusoidal time-varying value — stable and continuous."""
    return round(base + amp * math.sin(2 * math.pi * (time.time() + seed) / period), 2)

def _shift_elapsed_minutes():
    """Minutes elapsed since last 6 AM shift start."""
    t = time.time()
    hour_of_day = (t % 86400) / 3600
    shift_start_hour = 6.0
    elapsed = (hour_of_day - shift_start_hour) % 24
    return max(0, elapsed * 60)

def _units_produced(rate_per_hour, seed=0):
    """Deterministic units produced this shift based on elapsed time."""
    elapsed_hrs = _shift_elapsed_minutes() / 60
    base = int(rate_per_hour * elapsed_hrs)
    # Small noise from sin
    noise = int(5 * math.sin(time.time() * 0.07 + seed))
    return max(0, base + noise)

def _machine_live_state(machine_id, base_state):
    """
    Returns live machine state. Most machines stay at their base state.
    A few oscillate to create demo dynamism.
    """
    if base_state in ("fault", "maintenance"):
        return base_state
    # Hash to decide if this machine is in a "transient" pattern
    h = int(hashlib.md5(machine_id.encode()).hexdigest()[:4], 16) % 100
    if h < 15:  # ~15% of running machines have brief idle windows
        slot = int(time.time() / 45)  # Changes every 45 seconds
        slot_h = int(hashlib.md5(f"{machine_id}-{slot}".encode()).hexdigest()[:4], 16) % 100
        if slot_h < 20:
            return "idle"
    return base_state

def _live_oee(base_oee, machine_id):
    seed = int(hashlib.md5(machine_id.encode()).hexdigest()[:4], 16)
    return round(min(99.9, max(0, _sin_val(base_oee, 1.8, 120, seed))), 1)

def _live_temp(base_temp, machine_id):
    seed = int(hashlib.md5((machine_id + "t").encode()).hexdigest()[:4], 16)
    return round(_sin_val(base_temp, 1.5, 90, seed), 1)

def _live_cycle(base_ct, machine_id):
    seed = int(hashlib.md5((machine_id + "c").encode()).hexdigest()[:4], 16)
    return round(max(0.5, _sin_val(base_ct, 0.3, 60, seed)), 2)

# ── Unity Catalog Vision Inspection ────────────────────────────────────────────

INSPECTION_IMAGES = [
    {"id": "insp_001", "filename": "insp_001.png", "part": "Door Outer — RH Front",  "line": "B", "ground_truth": "clean"},
    {"id": "insp_002", "filename": "insp_002.png", "part": "Hood Outer Panel",        "line": "B", "ground_truth": "clean"},
    {"id": "insp_003", "filename": "insp_003.png", "part": "Roof Panel",              "line": "B", "ground_truth": "defective",
     "defect": "E-Coat Adhesion Failure", "bbox": [140, 152, 184, 196], "severity": "HIGH",   "confidence_sim": 0.942},
    {"id": "insp_004", "filename": "insp_004.png", "part": "Quarter Panel — RH",      "line": "B", "ground_truth": "clean"},
    {"id": "insp_005", "filename": "insp_005.png", "part": "Fender — LH Front",       "line": "B", "ground_truth": "clean"},
    {"id": "insp_006", "filename": "insp_006.png", "part": "Door Outer — LH Front",   "line": "B", "ground_truth": "clean"},
    {"id": "insp_007", "filename": "insp_007.png", "part": "Trunk Lid Panel",         "line": "B", "ground_truth": "defective",
     "defect": "E-Coat Adhesion Failure", "bbox": [173, 88, 213, 128], "severity": "MEDIUM", "confidence_sim": 0.886},
    {"id": "insp_008", "filename": "insp_008.png", "part": "Door Outer — LH Rear",    "line": "B", "ground_truth": "clean"},
    {"id": "insp_009", "filename": "insp_009.png", "part": "Quarter Panel — LH",      "line": "B", "ground_truth": "clean"},
    {"id": "insp_010", "filename": "insp_010.png", "part": "Fender — RH Front",       "line": "B", "ground_truth": "clean"},
]

def _uc_image_url(filename):
    return f"/Volumes/{UC_CATALOG}/{UC_SCHEMA}/{UC_VOLUME}/{filename}"

def _fetch_image_bytes(filename):
    """Fetch image bytes from UC Volume via Databricks Files API."""
    try:
        host, hdrs = _creds()
        file_hdrs = {k: v for k, v in hdrs.items() if k != "Content-Type"}
        r = requests.get(
            f"{host}/api/2.0/fs/files/Volumes/{UC_CATALOG}/{UC_SCHEMA}/{UC_VOLUME}/{filename}",
            headers=file_hdrs, timeout=15,
        )
        if r.status_code == 200:
            return r.content
    except Exception:
        pass
    # Fallback: local static file
    local = os.path.join(os.path.dirname(__file__), "static", "img", "inspection", filename)
    if os.path.exists(local):
        with open(local, "rb") as f:
            return f.read()
    return None

def _extract_features(image_bytes):
    """
    Extract 77-dim feature vector from PNG bytes.
    Must match the feature extraction used in train_defect_model.py exactly.
    """
    try:
        import io as _io
        import math as _math
        from PIL import Image as _PILImage
        import numpy as _np

        IMG_SIZE = 64
        img = _PILImage.open(_io.BytesIO(image_bytes)).convert("RGB")
        img = img.resize((IMG_SIZE, IMG_SIZE), _PILImage.LANCZOS)
        arr = _np.array(img).astype(_np.float32) / 255.0

        feats = []
        # 1. Per-channel mean + std (6)
        for c in range(3):
            ch = arr[:, :, c]
            feats += [float(ch.mean()), float(ch.std())]
        # 2. Per-channel histogram 16 bins (48)
        for c in range(3):
            hist, _ = _np.histogram(arr[:, :, c], bins=16, range=(0.0, 1.0))
            hist = hist.astype(_np.float32) / hist.sum()
            feats += hist.tolist()
        # 3. Dark-pixel ratio (1)
        feats.append(float((arr < 0.28).all(axis=2).mean()))
        # 4. Dark/bright contrast ratio (1)
        dark   = float((arr < 0.28).all(axis=2).sum())
        bright = float((arr > 0.72).all(axis=2).sum())
        feats.append(dark / max(1.0, bright + 1e-6))
        # 5. Gradient stats (2)
        gray = arr.mean(axis=2)
        gy, gx = _np.gradient(gray)
        grad = _np.sqrt(gx**2 + gy**2)
        feats += [float(grad.mean()), float(grad.std())]
        # 6. Quadrant means (12)
        mid = IMG_SIZE // 2
        for r0, r1 in [(0, mid), (mid, IMG_SIZE)]:
            for c0, c1 in [(0, mid), (mid, IMG_SIZE)]:
                region = arr[r0:r1, c0:c1]
                for ch in range(3):
                    feats.append(float(region[:, :, ch].mean()))
        # 7. Centre vs edge variance (2)
        pad = int(IMG_SIZE * 0.15)
        centre = arr[pad:-pad, pad:-pad]
        edge   = _np.concatenate([arr[:pad, :].reshape(-1, 3), arr[-pad:, :].reshape(-1, 3),
                                   arr[:, :pad, :].reshape(-1, 3), arr[:, -pad:, :].reshape(-1, 3)])
        feats += [float(centre.var()), float(edge.var())]
        # 8. Intensity range (2)
        feats += [float(arr.min()), float(arr.max())]
        # 9. Per-channel skewness (3)
        for c in range(3):
            ch = arr[:, :, c]
            mu, sigma = ch.mean(), ch.std() + 1e-6
            feats.append(float(((ch - mu) ** 3).mean() / sigma ** 3))

        return feats  # 77 features
    except Exception:
        return None


def _call_vision_endpoint(image_bytes, image_id, spec):
    """Call the Databricks 'vision' serving endpoint with extracted features."""
    feats = _extract_features(image_bytes)
    if feats is None:
        return None
    try:
        host, hdrs = _creds()
        # MLflow sklearn model expects dataframe_records with named columns
        payload = {"dataframe_records": [
            {f"x{i}": v for i, v in enumerate(feats)}
        ]}
        r = requests.post(
            f"{host}/serving-endpoints/{VISION_MODEL_ENDPOINT}/invocations",
            headers=hdrs,
            json=payload,
            timeout=20,
        )
        if r.status_code == 200:
            resp = r.json()
            # MLflow sklearn returns {"predictions": [0]} or {"predictions": ["clean"]}
            preds = resp.get("predictions", [])
            if preds:
                pred_val = preds[0]
                # Normalise: 0/1 int or "clean"/"defective" string
                if str(pred_val) in ("1", "defective"):
                    return {"prediction": "defective", "defect_type": spec.get("defect", "E-Coat Adhesion Failure"),
                            "confidence": 0.92, "severity": spec.get("severity", "HIGH"),
                            "bbox": spec.get("bbox"), "source": "model"}
                else:
                    return {"prediction": "clean", "defect_type": None,
                            "confidence": 0.96, "severity": None, "bbox": None, "source": "model"}
    except Exception:
        pass
    return None


def _simulate_inspect(spec):
    if spec["ground_truth"] == "clean":
        confidence = round(0.940 + (abs(hash(spec["id"])) % 58) / 1000.0, 3)
        return {"prediction": "clean", "defect_type": None, "confidence": confidence,
                "severity": None, "bbox": None}
    return {"prediction": "defective", "defect_type": spec["defect"],
            "confidence": spec["confidence_sim"], "severity": spec["severity"], "bbox": spec["bbox"]}

# ── Static Machine Definitions ─────────────────────────────────────────────────

MACHINES_STATIC = [
    # ── Line A: Body Shop — Vehicle Body Assemblies (VBA) ──────────────────────
    {
        "id": "BDY-STM-01", "line": "A", "line_name": "Body Shop",
        "name": "3,000-Ton Stamping Press", "product": "VBA",
        "base_state": "running", "base_oee": 56.4, "base_temp": 48.4,
        "std_cycle_sec": 6.0, "target_units_hr": 580,
        "description": "Progressive die stamping — hood, doors, roof, fenders, quarter panels",
        "sensor_tags": ["tonnage", "die_temp_c", "feed_rate_spm"],
    },
    {
        "id": "BDY-WLD-01", "line": "A", "line_name": "Body Shop",
        "name": "Robotic Welding Cell", "product": "VBA",
        "base_state": "fault", "base_oee": 0, "base_temp": 52.1,
        "std_cycle_sec": 90.0, "target_units_hr": 38,
        "fault_code": "E-1106",
        "fault_msg": "Electrode tip failure — weld current compensation exceeded 100% on robots 3, 7, 14. BIW weld quality out of spec.",
        "description": "24-robot body-in-white (BIW) cell — 3,500+ spot welds per body shell",
        "sensor_tags": ["weld_current_ka", "electrode_force_kn", "cycle_time_s"],
    },
    {
        "id": "BDY-SLD-01", "line": "A", "line_name": "Body Shop",
        "name": "Sealing & Hemming Station", "product": "VBA",
        "base_state": "fault", "base_oee": 0, "base_temp": 28.3,
        "std_cycle_sec": 45.0, "target_units_hr": 78,
        "fault_code": "E-3301",
        "fault_msg": "Hemming die misalignment — door flange gap 1.8mm vs. 0.5mm tolerance. 44 bodies queued.",
        "description": "Robotic seam sealing and door/hood/trunk hemming",
        "sensor_tags": ["sealant_flow_ml", "hem_force_kn", "gap_flush_mm"],
    },
    {
        "id": "BDY-INS-01", "line": "A", "line_name": "Body Shop",
        "name": "CMM Body Dimension Check", "product": "VBA",
        "base_state": "idle", "base_oee": 0, "base_temp": 22.1,
        "std_cycle_sec": 30.0, "target_units_hr": 118,
        "idle_reason": "WIP queue full — FAL-ASM-01 fault blocking all body throughput, 61 bodies accumulated upstream",
        "description": "Coordinate measurement machine — gap/flush and dimensional compliance audit",
        "sensor_tags": ["gap_mm", "flush_mm", "cpk_score"],
    },

    # ── Line B: Paint Shop — Painted Body Units (PBU) ──────────────────────────
    {
        "id": "PNT-PRP-01", "line": "B", "line_name": "Paint Shop",
        "name": "Phosphate Pre-Treatment", "product": "PBU",
        "base_state": "running", "base_oee": 58.9, "base_temp": 54.8,
        "std_cycle_sec": 120.0, "target_units_hr": 28,
        "description": "Multi-stage zinc phosphate wash and conversion coating for corrosion protection",
        "sensor_tags": ["bath_temp_c", "ph_level", "coating_weight_g_m2"],
    },
    {
        "id": "PNT-ECT-01", "line": "B", "line_name": "Paint Shop",
        "name": "E-Coat Tank (CED)", "product": "PBU",
        "base_state": "fault", "base_oee": 0, "base_temp": 30.2,
        "std_cycle_sec": 180.0, "target_units_hr": 18,
        "fault_code": "E-4401",
        "fault_msg": "Bath contamination — iron particulate 340 ppm vs. 50 ppm limit. 18-body carrier lot quarantined, tank draining.",
        "description": "Cathodic electro-deposition primer — full-cavity corrosion protection",
        "sensor_tags": ["voltage_v", "bath_temp_c", "film_thickness_um"],
    },
    {
        "id": "PNT-BSC-01", "line": "B", "line_name": "Paint Shop",
        "name": "Robotic Base Coat Booth", "product": "PBU",
        "base_state": "idle", "base_oee": 0, "base_temp": 25.4,
        "std_cycle_sec": 60.0, "target_units_hr": 58,
        "idle_reason": "Starved — PNT-ECT-01 bath contamination fault has halted all painted body units entering booth",
        "description": "12-robot waterborne base coat — color and metallic effect layers",
        "sensor_tags": ["film_build_um", "spray_pressure_bar", "transfer_efficiency_pct"],
    },
    {
        "id": "PNT-CLR-01", "line": "B", "line_name": "Paint Shop",
        "name": "Clear Coat & Bake Oven", "product": "PBU",
        "base_state": "idle", "base_oee": 0, "base_temp": 141.0,
        "std_cycle_sec": 1800.0, "target_units_hr": 2,
        "idle_reason": "No bodies in queue — Paint Shop offline due to E-Coat contamination fault upstream",
        "description": "High-solids clear coat application and 140°C bake oven cure cycle",
        "sensor_tags": ["oven_temp_c", "cure_time_min", "gloss_gu"],
    },
    {
        "id": "PNT-INS-01", "line": "B", "line_name": "Paint Shop",
        "name": "Paint Quality Inspection", "product": "PBU",
        "base_state": "maintenance", "base_oee": 0, "base_temp": 23.5,
        "std_cycle_sec": 20.0, "target_units_hr": 172,
        "maintenance_type": "Scheduled PM — wavescan vision calibration and LED lighting replacement (coinciding with E-Coat shutdown)",
        "description": "Automated paint defect detection: orange peel, runs, sags, contamination, mottling",
        "sensor_tags": ["defect_count", "wavescan_du", "doi_score"],
    },

    # ── Line C: Powertrain — Powertrain Modules (PTM) ──────────────────────────
    {
        "id": "PTN-MCH-01", "line": "C", "line_name": "Powertrain",
        "name": "CNC Block Machining Center", "product": "PTM",
        "base_state": "running", "base_oee": 63.2, "base_temp": 42.3,
        "std_cycle_sec": 120.0, "target_units_hr": 28,
        "description": "5-axis CNC machining — cylinder boring, honing, deck facing, lifter bore",
        "sensor_tags": ["spindle_load_pct", "coolant_temp_c", "tool_wear_pct"],
    },
    {
        "id": "PTN-HAD-01", "line": "C", "line_name": "Powertrain",
        "name": "Cylinder Head Assembly", "product": "PTM",
        "base_state": "running", "base_oee": 52.8, "base_temp": 31.7,
        "std_cycle_sec": 96.0, "target_units_hr": 36,
        "description": "Automated valve train assembly, cam bearing install, torque-to-yield fastening",
        "sensor_tags": ["torque_nm", "torque_angle_deg", "valve_clearance_mm"],
    },
    {
        "id": "PTN-BLD-01", "line": "C", "line_name": "Powertrain",
        "name": "Engine Build Station", "product": "PTM",
        "base_state": "fault", "base_oee": 0, "base_temp": 36.8,
        "std_cycle_sec": 240.0, "target_units_hr": 14,
        "fault_code": "E-5502",
        "fault_msg": "Torque angle fault — crankshaft main bearing cap torque not met. 18 engine builds halted.",
        "description": "Final engine assembly: block+head marriage, crankshaft, piston/ring install",
        "sensor_tags": ["torque_nm", "angle_deg", "crank_endplay_mm"],
    },
    {
        "id": "PTN-DYN-01", "line": "C", "line_name": "Powertrain",
        "name": "Cold Test Dyno Cell", "product": "PTM",
        "base_state": "running", "base_oee": 41.6, "base_temp": 58.4,
        "std_cycle_sec": 300.0, "target_units_hr": 11,
        "description": "Cold-test dynamometer — crankshaft rotation, compression, leak-down test",
        "sensor_tags": ["cold_crank_nm", "compression_bar", "leak_rate_cc_min"],
    },

    # ── Shared: Final Assembly — Finished Vehicles (VEH) ───────────────────────
    # All 3 upstream lines converge here. THIS IS THE ROOT CAUSE — FAL-ASM-01 down blocks everything.
    {
        "id": "FAL-ASM-01", "line": "S", "line_name": "Final Assembly",
        "name": "Final Assembly Line", "product": "VEH",
        "base_state": "fault", "base_oee": 0, "base_temp": 26.4,
        "std_cycle_sec": 60.0, "target_units_hr": 60,
        "fault_code": "E-7701",
        "fault_msg": "Conveyor sequencer fault — PLC watchdog timeout on transfer car #4. Line stopped 52 min. ALL upstream lines blocked.",
        "description": "Body+powertrain+paint marriage, trim install, glass, fluids, end-of-line QC gate",
        "sensor_tags": ["takt_time_s", "torque_completion_pct", "quality_gate_pass_rate"],
    },
]

# ── Static Alarm Definitions ────────────────────────────────────────────────────

ALARMS_STATIC = [
    {
        "id": "ALM-001", "machine_id": "FAL-ASM-01", "severity": "CRITICAL",
        "code": "E-7701", "message": "Conveyor sequencer fault — transfer car #4 PLC watchdog timeout. Final assembly line STOPPED for 52 min.",
        "category": "Equipment Fault", "triggered_min_ago": 52, "acknowledged": False,
        "impact": "ALL 3 LINES BLOCKED — VBA/PBU/PTM feed halted. 34 vehicles at risk. 60 vehicles/hr output at zero.",
        "ai_root_cause": "Conveyor PLC sequencer watchdog timeout caused by intermittent encoder signal loss on transfer car #4. Replace encoder assembly (Part #TC4-ENC-200), reset PLC sequence, and verify handshake with upstream accumulation conveyor.",
    },
    {
        "id": "ALM-002", "machine_id": "PNT-ECT-01", "severity": "CRITICAL",
        "code": "E-4401", "message": "E-Coat bath contamination — iron particulate 340 ppm vs. 50 ppm limit. 18-body carrier lot quarantined.",
        "category": "Quality Hold", "triggered_min_ago": 88, "acknowledged": False,
        "impact": "Paint Shop offline — 18 bodies quarantined for strip/re-coat. PBU throughput at zero for remainder of shift.",
        "ai_root_cause": "Phosphate pre-treatment rinse stage failure — iron dragout not neutralized before E-Coat immersion. Drain and replace bath (~4 hrs), acid-wash tank interior, re-qualify with test panel before resuming production.",
    },
    {
        "id": "ALM-003", "machine_id": "BDY-WLD-01", "severity": "CRITICAL",
        "code": "E-1106", "message": "Electrode tip failure — weld current compensation exceeded 100% limit on robots 3, 7, 14. BIW weld porosity confirmed.",
        "category": "Equipment Fault", "triggered_min_ago": 19, "acknowledged": False,
        "impact": "Robotic weld cell STOPPED — 26 bodies in queue, Body Shop at zero VBA output. All bodies since 08:40 on quality hold.",
        "ai_root_cause": "Electrode tip worn beyond compensation range — accelerated from high-strength steel alloy change 3 shifts ago. Immediate tip replacement on robots 3, 7, 14. Reduce dress interval from 800 to 500 welds going forward.",
    },
    {
        "id": "ALM-004", "machine_id": "BDY-SLD-01", "severity": "CRITICAL",
        "code": "E-3301", "message": "Hemming die misalignment — door flange gap 1.8mm vs. 0.5mm tolerance. 44 bodies queued.",
        "category": "Equipment Fault", "triggered_min_ago": 134, "acknowledged": False,
        "impact": "Sealing station halted for 2h 14m — 44 VBA in queue, ongoing 78 bodies/hr capacity loss",
        "ai_root_cause": "Hemming die cam follower wear on door station 2. Replace cam follower assembly (Part #HD-CFW-44), re-shim die, and re-qualify gap/flush to within 0.3mm before restart.",
    },
    {
        "id": "ALM-005", "machine_id": "PTN-BLD-01", "severity": "CRITICAL",
        "code": "E-5502", "message": "Crankshaft main bearing cap torque angle 63° vs. 78° target — torque fault. 18 engine builds halted.",
        "category": "Equipment Fault", "triggered_min_ago": 67, "acknowledged": False,
        "impact": "Engine build stopped — 18 PTM units halted, powertrain feed dropping. Cold test failure rate now 43% on completed engines.",
        "ai_root_cause": "Torque wrench transducer calibration drift on assembly spindle #3. Recalibrate against master torque standard. All engines built after 07:20 require torque re-verification before dyno test.",
    },
    {
        "id": "ALM-006", "machine_id": "PTN-DYN-01", "severity": "HIGH",
        "code": "W-6601", "message": "Cold test failure rate 43% this shift — cylinder 3 compression below spec on multiple engines.",
        "category": "Quality Risk", "triggered_min_ago": 41, "acknowledged": True,
        "impact": "43% of completed engines failing dyno — 3.2 hr rework loop per engine consuming all available dyno time",
        "ai_root_cause": "Head gasket seating failures traced to undertorqued main bearing caps from PTN-BLD-01 fault. All engines built after 07:20 to be re-inspected per quality hold QH-2024-047.",
    },
    {
        "id": "ALM-007", "machine_id": "PTN-MCH-01", "severity": "MEDIUM",
        "code": "W-3302", "message": "Tool wear at 94% of replacement threshold — spindle #4 bore diameter trending to lower control limit.",
        "category": "Maintenance Due", "triggered_min_ago": 95, "acknowledged": True,
        "impact": "SPC chart out of control — bore diameter Cpk 0.84, below 1.33 target. Quality risk in next 40 parts.",
        "ai_root_cause": "Accelerated wear from coolant concentration drop to 6% (target 8-9%). Correct coolant concentration immediately and replace spindle #4 insert before next 40 parts.",
    },
]

# ── Live Endpoint ──────────────────────────────────────────────────────────────

def _build_live_machines():
    machines = []
    for m in MACHINES_STATIC:
        live_state = _machine_live_state(m["id"], m["base_state"])
        is_running = live_state == "running"
        seed = int(hashlib.md5(m["id"].encode()).hexdigest()[:4], 16)

        units = _units_produced(m["target_units_hr"], seed) if is_running else 0
        oee   = _live_oee(m["base_oee"], m["id"]) if is_running else 0
        temp  = _live_temp(m["base_temp"], m["id"])
        cycle = _live_cycle(m["std_cycle_sec"], m["id"]) if is_running else m["std_cycle_sec"]

        machines.append({
            "id":             m["id"],
            "line":           m["line"],
            "line_name":      m["line_name"],
            "name":           m["name"],
            "product":        m["product"],
            "state":          live_state,
            "oee":            oee,
            "temp":           temp,
            "cycle_time_sec": cycle,
            "units_this_shift": units,
            "target_units_hr": m["target_units_hr"],
            "fault_code":     m.get("fault_code"),
            "fault_msg":      m.get("fault_msg"),
            "idle_reason":    m.get("idle_reason"),
            "maintenance_type": m.get("maintenance_type"),
            "description":    m["description"],
        })
    return machines


def _compute_plant_kpi(machines):
    running   = [m for m in machines if m["state"] == "running"]
    faults    = [m for m in machines if m["state"] == "fault"]
    idle      = [m for m in machines if m["state"] == "idle"]
    maint     = [m for m in machines if m["state"] == "maintenance"]

    oee_running = [m["oee"] for m in running if m["oee"] > 0]
    plant_oee   = round(sum(oee_running) / len(oee_running), 1) if oee_running else 0

    vba_machines = [m for m in machines if m["product"] == "VBA"]
    pbu_machines = [m for m in machines if m["product"] == "PBU"]
    ptm_machines = [m for m in machines if m["product"] == "PTM"]

    total_alarms    = len(ALARMS_STATIC)
    crit_alarms     = sum(1 for a in ALARMS_STATIC if a["severity"] == "CRITICAL")
    unacked_alarms  = sum(1 for a in ALARMS_STATIC if not a["acknowledged"])

    shift_vba = sum(m["units_this_shift"] for m in vba_machines if m["state"] == "running")
    shift_pbu = sum(m["units_this_shift"] for m in pbu_machines if m["state"] == "running")
    shift_ptm = sum(m["units_this_shift"] for m in ptm_machines if m["state"] == "running")

    return {
        "total_machines":    len(machines),
        "running":           len(running),
        "fault":             len(faults),
        "idle":              len(idle),
        "maintenance":       len(maint),
        "plant_oee":         plant_oee,
        "oee_target":        85.0,
        "total_alarms":      total_alarms,
        "critical_alarms":   crit_alarms,
        "unacknowledged":    unacked_alarms,
        "vba_shift_units":   shift_vba,
        "vba_target_shift":  420,
        "pbu_shift_units":   shift_pbu,
        "pbu_target_shift":  180,
        "ptm_shift_units":   shift_ptm,
        "ptm_target_shift":  240,
        "shift_elapsed_min": round(_shift_elapsed_minutes(), 0),
    }


# ── OEE Trend Data (static — last 7 shifts) ────────────────────────────────────

OEE_TREND = [
    {"shift": "Mon D", "plant": 78.2, "line_a": 81.4, "line_b": 76.8, "line_c": 79.1},
    {"shift": "Mon N", "plant": 75.4, "line_a": 78.2, "line_b": 73.1, "line_c": 75.3},
    {"shift": "Tue D", "plant": 71.8, "line_a": 74.6, "line_b": 70.2, "line_c": 72.5},
    {"shift": "Tue N", "plant": 68.3, "line_a": 72.1, "line_b": 65.4, "line_c": 68.9},
    {"shift": "Wed D", "plant": 63.4, "line_a": 68.8, "line_b": 59.7, "line_c": 65.1},
    {"shift": "Wed N", "plant": 57.2, "line_a": 63.4, "line_b": 52.1, "line_c": 58.8},
    {"shift": "Thu D", "plant": 46.4, "line_a": 54.2, "line_b": 38.6, "line_c": 48.7},
]

# ── Downtime Pareto ────────────────────────────────────────────────────────────

DOWNTIME_PARETO = [
    {"reason": "Final Assembly Conveyor Fault",  "minutes": 312, "pct": 38.2},
    {"reason": "Equipment Fault (BDY / PTN)",    "minutes": 241, "pct": 29.5},
    {"reason": "E-Coat Bath Contamination Hold", "minutes": 148, "pct": 18.1},
    {"reason": "Quality Rework / Retest Loop",   "minutes": 82,  "pct": 10.0},
    {"reason": "Planned Maintenance",            "minutes": 34,  "pct": 4.2},
]

MACHINE_MTBF = [
    {"id": "FAL-ASM-01", "mtbf_hrs": 48,  "mttr_hrs": 4.2, "failures_ytd": 38, "flagged": True},
    {"id": "BDY-SLD-01", "mtbf_hrs": 52,  "mttr_hrs": 3.8, "failures_ytd": 32, "flagged": True},
    {"id": "PNT-ECT-01", "mtbf_hrs": 61,  "mttr_hrs": 5.1, "failures_ytd": 27, "flagged": True},
    {"id": "PTN-BLD-01", "mtbf_hrs": 78,  "mttr_hrs": 2.8, "failures_ytd": 26, "flagged": True},
    {"id": "BDY-WLD-01", "mtbf_hrs": 98,  "mttr_hrs": 1.6, "failures_ytd": 22, "flagged": True},
    {"id": "PTN-DYN-01", "mtbf_hrs": 184, "mttr_hrs": 1.2, "failures_ytd": 14},
    {"id": "PTN-MCH-01", "mtbf_hrs": 228, "mttr_hrs": 2.1, "failures_ytd": 9},
    {"id": "BDY-STM-01", "mtbf_hrs": 312, "mttr_hrs": 1.6, "failures_ytd": 4},
]

# ── Quality Data ───────────────────────────────────────────────────────────────

QUALITY_SUMMARY = {
    "total_inspected_shift": 2840,
    "total_passed_shift":    2186,
    "total_scrap_shift":     224,
    "total_rework_shift":    430,
    "first_pass_yield":      76.9,
    "scrap_rate_pct":        7.9,
    "rework_rate_pct":       15.1,
    "target_fpy":            98.5,
}

DEFECT_TYPES = [
    {"type": "E-Coat Adhesion Failure",   "count": 187, "line": "B", "pct": 38.2},
    {"type": "Weld Porosity / Spatter",   "count": 124, "line": "A", "pct": 25.4},
    {"type": "Torque Non-Conformance",    "count": 88,  "line": "C", "pct": 18.0},
    {"type": "Hemming Dimensional",       "count": 52,  "line": "A", "pct": 10.6},
    {"type": "Paint Surface Contam.",     "count": 28,  "line": "B", "pct": 5.7},
    {"type": "Other",                     "count": 10,  "line": "C", "pct": 2.0},
]

# ── AI Recommendation ──────────────────────────────────────────────────────────

def _generate_ai_recommendation(machine_id: str) -> str:
    machine = next((m for m in MACHINES_STATIC if m["id"] == machine_id), None)
    alarms  = [a for a in ALARMS_STATIC if a["machine_id"] == machine_id]
    if not machine:
        return "Machine not found."

    try:
        host, hdrs = _creds()
        alarm_text = "\n".join(f"- [{a['severity']}] {a['message']}" for a in alarms) or "No active alarms."
        prompt = (
            f"You are the Databricks Manufacturing Intelligence AI — an expert in automotive "
            f"manufacturing operations. Generate a precise root cause analysis and action plan.\n\n"
            f"MACHINE: {machine['id']} — {machine['name']}\n"
            f"LINE: {machine['line_name']}\n"
            f"PRODUCT: {machine['product']}\n"
            f"CURRENT STATE: {machine['base_state'].upper()}\n"
            f"DESCRIPTION: {machine['description']}\n"
            f"SENSOR TAGS: {', '.join(machine['sensor_tags'])}\n\n"
            f"ACTIVE ALARMS:\n{alarm_text}\n\n"
            f"Generate your analysis in EXACTLY this format:\n"
            f"**ROOT CAUSE:** [1-2 sentences. Be specific about the failure mechanism.]\n"
            f"**CONFIDENCE:** [X%]\n"
            f"**IMMEDIATE ACTIONS (Next 30 Minutes):**\n"
            f"- [Action 1 — Owner: Technician]\n"
            f"- [Action 2 — Owner: Process Engineer]\n"
            f"- [Action 3 — Owner: Quality]\n"
            f"**PARTS REQUIRED:** [Specific part numbers or descriptions]\n"
            f"**EST. REPAIR TIME:** [X hours]\n"
            f"**PRODUCTION RECOVERY PLAN:** [How to recover lost units]\n"
            f"**PREVENTIVE ACTION:** [Long-term fix to prevent recurrence]\n\n"
            f"Use manufacturing engineering precision. Reference specific technical parameters."
        )
        r = requests.post(
            f"{host}/serving-endpoints/{LLM_ENDPOINT}/invocations",
            headers=hdrs,
            json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 500, "temperature": 0.2},
            timeout=50,
        )
        if r.status_code == 200:
            return r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception:
        pass

    # Deterministic fallback
    alarm = alarms[0] if alarms else {}
    return (
        f"**ROOT CAUSE:** {alarm.get('ai_root_cause', 'Component degradation detected via sensor pattern analysis. Maintenance inspection required.')}\n\n"
        f"**CONFIDENCE:** 87%\n\n"
        f"**IMMEDIATE ACTIONS (Next 30 Minutes):**\n"
        f"- Isolate machine and place LOTO (Lockout/Tagout) — Technician\n"
        f"- Pull fault diagnostics from machine controller and cross-reference with Databricks sensor log — Process Engineer\n"
        f"- Place quality hold on any units produced in the 30 min prior to fault — Quality Engineer\n\n"
        f"**PARTS REQUIRED:** Refer to machine BOM in Maintenance module — check spare parts inventory in Databricks Unity Catalog\n\n"
        f"**EST. REPAIR TIME:** 2–4 hours\n\n"
        f"**PRODUCTION RECOVERY PLAN:** Reroute affected WIP to redundant station if available. Prioritize vehicles closest to Final Assembly completion first.\n\n"
        f"**PREVENTIVE ACTION:** Increase PM frequency based on MTBF trend. Add sensor threshold alert in Databricks IoT pipeline."
    )


# ── Genie / LLM Chat Proxy ────────────────────────────────────────────────────

POLL_INTERVAL = 3
MAX_WAIT      = 120


def _poll_genie(host, hdrs, space_id, conversation_id, message_id):
    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        r = requests.get(
            f"{host}/api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}/messages/{message_id}",
            headers=hdrs, timeout=30,
        )
        if r.status_code == 200:
            msg = r.json()
            if msg.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
                return msg
        time.sleep(POLL_INTERVAL)
    return None


def _extract_answer(msg):
    if not msg:
        return "No response received."
    for att in msg.get("attachments", []):
        content = (att.get("text") or {}).get("content") or att.get("content")
        if content:
            return content
    return msg.get("content", "No answer returned.")


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if not session.get("authenticated"):
        return redirect("/login")
    return send_from_directory("static", "index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    # Auto-auth via URL params (launched from portal)
    if request.method == "GET":
        auto_user    = request.args.get("auto_user", "").strip()
        auto_company = request.args.get("auto_company", "").strip()
        if auto_user and auto_company:
            session["authenticated"] = True
            session["username"]       = auto_user
            session["company_name"]   = auto_company
            return redirect("/")

    error = None
    if request.method == "POST":
        username     = (request.form.get("username") or "").strip()
        company_name = (request.form.get("password") or "").strip()
        if username and company_name:
            session["authenticated"] = True
            session["username"]       = username
            session["company_name"]   = company_name
            return redirect("/")
        else:
            error = "Please enter your name and company to continue."

    return send_from_directory("static", "login.html"), 200 if not error else 401

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/api/live")
def get_live():
    if SQL_WAREHOUSE_HTTP_PATH:
        gold = _gold_machine_state()
        if gold:
            kpi = _compute_plant_kpi(gold)
            return jsonify({"machines": gold, "kpi": kpi, "ts": int(time.time()), "source": "gold"})
    machines = _build_live_machines()
    kpi      = _compute_plant_kpi(machines)
    return jsonify({"machines": machines, "kpi": kpi, "ts": int(time.time()), "source": "sim"})


@app.route("/api/alarms")
def get_alarms():
    if SQL_WAREHOUSE_HTTP_PATH:
        gold = _gold_alarms()
        if gold is not None:
            return jsonify(gold)
    return jsonify(ALARMS_STATIC)


@app.route("/api/downtime")
def get_downtime():
    if SQL_WAREHOUSE_HTTP_PATH:
        pareto, mtbf = _gold_downtime()
        if pareto and mtbf:
            return jsonify({"pareto": pareto, "mtbf": mtbf})
    return jsonify({"pareto": DOWNTIME_PARETO, "mtbf": MACHINE_MTBF})


@app.route("/api/oee-trend")
def get_oee_trend():
    if SQL_WAREHOUSE_HTTP_PATH:
        gold = _gold_oee_trend()
        if gold:
            return jsonify(gold)
    return jsonify(OEE_TREND)


@app.route("/api/quality")
def get_quality():
    if SQL_WAREHOUSE_HTTP_PATH:
        summary, defects = _gold_quality()
        if summary and defects:
            return jsonify({"summary": summary, "defects": defects})
    return jsonify({"summary": QUALITY_SUMMARY, "defects": DEFECT_TYPES})


@app.route("/api/diagnose/<machine_id>")
def diagnose_machine(machine_id):
    rec = _generate_ai_recommendation(machine_id)
    return jsonify({"machine_id": machine_id, "recommendation": rec})


@app.route("/api/ask", methods=["POST"])
def ask_shift():
    data            = request.get_json(force=True) or {}
    question        = data.get("question", "").strip()
    conversation_id = data.get("conversation_id") or None

    if not question:
        return jsonify({"error": "No question provided"}), 400

    machines = _build_live_machines()
    kpi      = _compute_plant_kpi(machines)

    if not GENIE_SPACE_ID:
        try:
            host, hdrs = _creds()
            context = (
                f"You are SHIFT, the Databricks Manufacturing Intelligence AI. "
                f"You help engineers and operators at an automotive manufacturing plant. "
                f"The plant makes 3 products: Vehicle Body Assemblies (VBA) on Line A, "
                f"Painted Body Units (PBU) on Line B, and Powertrain Modules (PTM) on Line C. "
                f"All 3 lines converge at the shared Final Assembly Line (FAL-ASM-01).\n\n"
                f"CURRENT PLANT STATUS:\n"
                f"- Plant OEE: {kpi['plant_oee']}% (target: {kpi['oee_target']}%)\n"
                f"- Machines Running: {kpi['running']}/{kpi['total_machines']}\n"
                f"- Active Faults: {kpi['fault']} machines down\n"
                f"- Critical Alarms: {kpi['critical_alarms']} unresolved\n"
                f"- VBA Output This Shift: {kpi['vba_shift_units']} / {kpi['vba_target_shift']} target\n"
                f"- PBU Output This Shift: {kpi['pbu_shift_units']} / {kpi['pbu_target_shift']} target\n"
                f"- PTM Output This Shift: {kpi['ptm_shift_units']} / {kpi['ptm_target_shift']} target\n\n"
                f"ACTIVE FAULTS:\n"
            )
            for a in ALARMS_STATIC:
                if a["severity"] == "CRITICAL":
                    context += f"- {a['machine_id']}: {a['message']} | AI Root Cause: {a['ai_root_cause']}\n"

            context += f"\nAnswer with manufacturing precision and specific technical recommendations: {question}"

            r = requests.post(
                f"{host}/serving-endpoints/{LLM_ENDPOINT}/invocations",
                headers=hdrs,
                json={"messages": [{"role": "user", "content": context}], "max_tokens": 500, "temperature": 0.3},
                timeout=50,
            )
            if r.status_code == 200:
                answer = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                return jsonify({
                    "answer": answer,
                    "conversation_id": None,
                    "source": "LLM",
                    "follow_ups": [
                        "Which machine has the worst MTBF this month?",
                        "What is the projected shift output if faults are resolved in 2 hours?",
                        "Which defect type is causing the most scrap on Line B?",
                    ],
                })
        except Exception:
            pass

        return jsonify({
            "answer": (
                f"**SHIFT Intelligence — Plant Status**\n\n"
                f"*Genie not configured — live operational summary:*\n\n"
                f"**Plant OEE:** {kpi['plant_oee']}% vs. {kpi['oee_target']}% target ⚠ CRITICAL\n\n"
                f"**Machine Status:** {kpi['running']} running | {kpi['fault']} fault | "
                f"{kpi['idle']} idle | {kpi['maintenance']} maintenance\n\n"
                f"**Root Cause:** FAL-ASM-01 conveyor fault (52 min) has cascaded — ALL 3 lines blocked. "
                f"PNT-ECT-01 bath contamination and BDY-WLD-01 electrode failure compound the stoppage.\n\n"
                f"**Shift Output:** VBA {kpi['vba_shift_units']}/{kpi['vba_target_shift']} | "
                f"PBU {kpi['pbu_shift_units']}/{kpi['pbu_target_shift']} | "
                f"PTM {kpi['ptm_shift_units']}/{kpi['ptm_target_shift']}\n\n"
                f"**Quality:** FPY 76.9% vs. 98.5% target — 224 scrapped, 430 rework units this shift.\n\n"
                f"Set `GENIE_SPACE_ID` in app.yaml for live Delta Lake queries."
            ),
            "conversation_id": None,
            "source": "demo",
            "follow_ups": [
                "What is the total vehicle output loss from the FAL-ASM-01 conveyor fault?",
                "Which fault should be resolved first to recover the most throughput?",
                "Why is the cold test dyno failure rate at 43% this shift?",
            ],
        })

    try:
        host, hdrs = _creds()
    except KeyError as e:
        return jsonify({"error": f"Missing env var: {e}"}), 500

    try:
        prefix = (
            "You are the SHIFT manufacturing intelligence assistant at an automotive manufacturing plant. "
            "The plant runs 3 lines: Body Shop (VBA), Paint Shop (PBU), Powertrain (PTM), converging at shared Final Assembly (FAL-ASM-01). "
            "Answer questions about shop floor OEE, machine health, quality, downtime, and production output. "
            "Use precise automotive manufacturing terminology."
        )
        full_q = prefix + " " + question

        if conversation_id:
            r = requests.post(
                f"{host}/api/2.0/genie/spaces/{GENIE_SPACE_ID}/conversations/{conversation_id}/messages",
                headers=hdrs, json={"content": full_q}, timeout=30,
            )
        else:
            r = requests.post(
                f"{host}/api/2.0/genie/spaces/{GENIE_SPACE_ID}/start-conversation",
                headers=hdrs, json={"content": full_q}, timeout=30,
            )

        if r.status_code not in (200, 201):
            return jsonify({"error": f"Genie error {r.status_code}"}), 502

        resp_json       = r.json()
        conversation_id = resp_json.get("conversation_id") or conversation_id
        message_id      = resp_json.get("message_id") or resp_json.get("id")
        msg             = _poll_genie(host, hdrs, GENIE_SPACE_ID, conversation_id, message_id)
        answer          = _extract_answer(msg)

        return jsonify({
            "answer": answer,
            "conversation_id": conversation_id,
            "source": "genie",
            "follow_ups": [
                "Which machine has the worst MTBF?",
                "What is the shift OEE trend for Line A?",
                "Show me the top 3 defect types this week.",
            ],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/inspection/images")
def list_inspection_images():
    return jsonify([
        {"id": img["id"], "filename": img["filename"], "part": img["part"],
         "uc_path": _uc_image_url(img["filename"])}
        for img in INSPECTION_IMAGES
    ])


@app.route("/api/inspection/image/<image_id>")
def get_inspection_image(image_id):
    """Proxy image from UC Volume (with local fallback)."""
    from flask import Response
    spec = next((img for img in INSPECTION_IMAGES if img["id"] == image_id), None)
    if not spec:
        return jsonify({"error": "Unknown image ID"}), 404
    data = _fetch_image_bytes(spec["filename"])
    if data:
        return Response(data, mimetype="image/png",
                        headers={"Cache-Control": "public, max-age=3600"})
    return jsonify({"error": "Image not found in UC Volume or local fallback"}), 404


@app.route("/api/inspect/<image_id>")
def inspect_image(image_id):
    """Run E-Coat defect detection via Databricks Model Serving (or simulation)."""
    spec = next((img for img in INSPECTION_IMAGES if img["id"] == image_id), None)
    if not spec:
        return jsonify({"error": "Unknown image ID"}), 404

    result = None

    # Try real Databricks vision endpoint
    if VISION_MODEL_ENDPOINT:
        image_bytes = _fetch_image_bytes(spec["filename"])
        if image_bytes:
            result = _call_vision_endpoint(image_bytes, image_id, spec)

    if result is None:
        result = _simulate_inspect(spec)
        result["source"] = "sim"

    return jsonify({
        "image_id":   image_id,
        "filename":   spec["filename"],
        "part":       spec["part"],
        "model":      VISION_MODEL_ENDPOINT or "databricks-ecoat-defect-v2",
        "uc_volume":  f"/Volumes/{UC_CATALOG}/{UC_SCHEMA}/{UC_VOLUME}",
        **result,
    })


# ── Production Impact Analysis ──────────────────────────────────────────────────

# Deterministic fallback impact data per image
_IMPACT_DATA = {
    "insp_003": {
        "decision": "SCRAP",
        "severity": "HIGH",
        "machine_time": [
            {"station": "E-Coat Strip & Clean",   "minutes": 45},
            {"station": "Phosphate Pre-Treatment", "minutes": 30},
            {"station": "E-Coat Re-dip",           "minutes": 60},
            {"station": "Base Coat",               "minutes": 25},
            {"station": "Clear Coat",              "minutes": 20},
            {"station": "Final Inspection",        "minutes": 15},
        ],
        "total_minutes": 195,
        "materials": [
            {"name": "DP780 AHSS Blank (new)",        "quantity": "1 panel (18.4 kg)"},
            {"name": "Phosphate Solution",             "quantity": "2.1 L"},
            {"name": "E-Coat Bath Replenishment",      "quantity": "0.8 L"},
            {"name": "Base Coat (Silver-Blue Met.)",   "quantity": "180 mL"},
            {"name": "Clear Coat (2K HS)",             "quantity": "120 mL"},
            {"name": "Strip Solvent (methyl acetate)", "quantity": "1.5 L"},
        ],
        "estimated_cost": "$1,240",
        "summary": "HIGH severity adhesion failure — panel has delamination extending below the primer interface. Strip-and-re-coat is not viable; a new DP780 AHSS stamped blank must be sourced from stamping. Full E-Coat line cycle required on replacement.",
    },
    "insp_007": {
        "decision": "REWORK",
        "severity": "MEDIUM",
        "machine_time": [
            {"station": "Localised Strip & Feather", "minutes": 20},
            {"station": "Spot Phosphate Treatment",  "minutes": 15},
            {"station": "Spot E-Coat Touch-Up",      "minutes": 35},
            {"station": "Base Coat Blend",           "minutes": 20},
            {"station": "Clear Coat Blend",          "minutes": 18},
            {"station": "Final Inspection",          "minutes": 10},
        ],
        "total_minutes": 118,
        "materials": [
            {"name": "Phosphate Solution",            "quantity": "0.4 L"},
            {"name": "E-Coat Touch-Up Compound",      "quantity": "150 mL"},
            {"name": "Base Coat (Silver-Blue Met.)",  "quantity": "90 mL"},
            {"name": "Clear Coat (2K HS)",            "quantity": "70 mL"},
            {"name": "Strip Solvent (spot use)",      "quantity": "0.3 L"},
        ],
        "estimated_cost": "$385",
        "summary": "MEDIUM severity adhesion failure — defect is localised (32×32 px zone, trunk lid upper quadrant). Spot rework viable without full strip. No new steel required. Estimated 2h throughput loss at PNT-ECT-01.",
    },
}


@app.route("/api/impact/<image_id>")
def get_production_impact(image_id):
    """Return production impact analysis for a defective image (LLM or deterministic)."""
    spec = next((img for img in INSPECTION_IMAGES if img["id"] == image_id), None)
    if not spec or spec.get("ground_truth") != "defective":
        return jsonify({"error": "No defect data for this image"}), 404

    fallback = _IMPACT_DATA.get(image_id)

    # Try LLM for a richer summary
    try:
        host, hdrs = _creds()
        fb = fallback or {}
        prompt = (
            f"You are a manufacturing quality engineer at an automotive paint shop. "
            f"An E-Coat adhesion failure has been detected on a {spec['part']} "
            f"(severity: {spec.get('severity', 'MEDIUM')}, defect: {spec.get('defect', 'E-Coat Adhesion Failure')}). "
            f"Decision: {fb.get('decision', 'REWORK')}. "
            f"Total rework time: {fb.get('total_minutes', 120)} minutes. "
            f"In 2 concise sentences, explain why this decision was made and what the main production risk is. "
            f"Do not repeat the decision or time — focus on root cause and risk."
        )
        r = requests.post(
            f"{host}/serving-endpoints/{LLM_ENDPOINT}/invocations",
            headers=hdrs,
            json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 120, "temperature": 0.3},
            timeout=15,
        )
        if r.status_code == 200:
            llm_summary = r.json()["choices"][0]["message"]["content"].strip()
            result = {**fallback, "part": spec["part"], "image_id": image_id, "summary": llm_summary}
            return jsonify(result)
    except Exception:
        pass

    if fallback:
        return jsonify({**fallback, "part": spec["part"], "image_id": image_id})

    return jsonify({"error": "Impact data unavailable"}), 500


# ── Predictive Maintenance ──────────────────────────────────────────────────────

PDM_FEATURE_COLS = [
    "temp_c", "vibration_rms", "spindle_load_pct", "oil_pressure_bar",
    "cycle_time_deviation_pct", "operating_hours", "hours_since_last_pm",
    "fault_count_7d", "alarm_count_24h",
]

# Deterministic risk profiles matching the cascade failure story.
# failure_prob drives risk_level and hours_to_failure.
_PDM_PROFILES = {
    "FAL-ASM-01": {"failure_prob": 0.97, "hours_to_failure": 0.0,  "fault_count_7d": 8,  "alarm_count_24h": 12, "action": "IMMEDIATE: Replace transfer car #4 encoder (Part #TC4-ENC-200) and reset PLC sequence."},
    "BDY-WLD-01": {"failure_prob": 0.94, "hours_to_failure": 0.0,  "fault_count_7d": 6,  "alarm_count_24h": 9,  "action": "IMMEDIATE: Replace electrode tips on robots 3, 7, 14. Run weld quality audit before restart."},
    "PNT-ECT-01": {"failure_prob": 0.91, "hours_to_failure": 0.0,  "fault_count_7d": 5,  "alarm_count_24h": 8,  "action": "IMMEDIATE: Drain bath, acid-wash tank, replace with fresh CED solution. ~4 hr recovery."},
    "PTN-BLD-01": {"failure_prob": 0.87, "hours_to_failure": 0.0,  "fault_count_7d": 5,  "alarm_count_24h": 7,  "action": "IMMEDIATE: Inspect torque tooling on main bearing cap station. Replace torque transducer."},
    "BDY-SLD-01": {"failure_prob": 0.83, "hours_to_failure": 0.0,  "fault_count_7d": 4,  "alarm_count_24h": 6,  "action": "IMMEDIATE: Re-calibrate hemming die alignment. Inspect door flange tooling for wear."},
    "PTN-MCH-01": {"failure_prob": 0.62, "hours_to_failure": 8.4,  "fault_count_7d": 3,  "alarm_count_24h": 4,  "action": "URGENT (next 8 hrs): Replace boring head insert and check spindle bearing preload. Coolant flow low."},
    "PTN-DYN-01": {"failure_prob": 0.41, "hours_to_failure": 18.2, "fault_count_7d": 2,  "alarm_count_24h": 2,  "action": "MONITOR: Schedule dynamometer coupling inspection at next scheduled PM window."},
    "BDY-STM-01": {"failure_prob": 0.31, "hours_to_failure": 28.6, "fault_count_7d": 1,  "alarm_count_24h": 1,  "action": "MONITOR: Die lubrication system showing intermittent pressure drops. Check lubricant reservoir."},
    "PTN-HAD-01": {"failure_prob": 0.26, "hours_to_failure": 36.1, "fault_count_7d": 1,  "alarm_count_24h": 1,  "action": "ROUTINE: Valve clearance measurement due. Schedule at next shift change."},
    "PNT-PRP-01": {"failure_prob": 0.22, "hours_to_failure": 42.0, "fault_count_7d": 1,  "alarm_count_24h": 0,  "action": "ROUTINE: Bath pH trending toward upper limit. Plan chemistry adjustment within 48 hrs."},
    "BDY-INS-01": {"failure_prob": 0.14, "hours_to_failure": 72.0, "fault_count_7d": 0,  "alarm_count_24h": 0,  "action": "OK: No maintenance action required. Next PM in 210 hrs."},
    "PNT-BSC-01": {"failure_prob": 0.12, "hours_to_failure": 88.0, "fault_count_7d": 0,  "alarm_count_24h": 0,  "action": "OK: Spray robot arm calibration recommended at next PM. No immediate action."},
    "PNT-CLR-01": {"failure_prob": 0.10, "hours_to_failure": 96.0, "fault_count_7d": 0,  "alarm_count_24h": 0,  "action": "OK: Oven temperature profile nominal. No action required."},
    "PNT-INS-01": {"failure_prob": 0.08, "hours_to_failure": 120.0,"fault_count_7d": 0,  "alarm_count_24h": 0,  "action": "OK: PM in progress. Return to service after wavescan recalibration complete."},
}

def _risk_level(prob):
    if prob >= 0.80: return "CRITICAL"
    if prob >= 0.55: return "HIGH"
    if prob >= 0.30: return "MEDIUM"
    return "LOW"

def _risk_color(level):
    return {"CRITICAL": "#ef4444", "HIGH": "#f97316", "MEDIUM": "#f59e0b", "LOW": "#22c55e"}[level]

def _pdm_features_from_machine(m, profile):
    """Build feature vector from live machine state + profile."""
    seed = int(hashlib.md5(m["id"].encode()).hexdigest()[:4], 16)
    rng  = seed / 65535.0  # 0→1 deterministic float
    return {
        "temp_c":                  _live_temp(m.get("base_temp", 40.0), m["id"]),
        "vibration_rms":           round(1.8 + profile.get("failure_prob", 0.1) * 3.2 + (rng - 0.5) * 0.3, 3),
        "spindle_load_pct":        round(min(100, m.get("base_oee", 60) * 0.9 + profile.get("failure_prob", 0.1) * 22), 1),
        "oil_pressure_bar":        round(max(0.5, 4.5 - profile.get("failure_prob", 0.1) * 2.8 + (rng - 0.5) * 0.2), 2),
        "cycle_time_deviation_pct":round(profile.get("failure_prob", 0.1) * 28.0 + (rng - 0.5) * 2.0, 2),
        "operating_hours":         round(8000 + (seed % 20000), 1),
        "hours_since_last_pm":     round(200 + profile.get("failure_prob", 0.1) * 2800, 1),
        "fault_count_7d":          profile.get("fault_count_7d", 0),
        "alarm_count_24h":         profile.get("alarm_count_24h", 0),
    }

def _call_pdm_endpoint(features_list):
    """Call PDM Model Serving endpoint. Returns list of failure_prob floats or None."""
    try:
        host, hdrs = _creds()
        import pandas as _pd
        payload = {"dataframe_records": features_list}
        r = requests.post(
            f"{host}/serving-endpoints/{PDM_ENDPOINT}/invocations",
            headers=hdrs, json=payload, timeout=12,
        )
        if r.status_code == 200:
            preds = r.json().get("predictions", [])
            # Model returns 0/1; use predict_proba if available via dataframe_split
            return [float(p) for p in preds]
    except Exception:
        pass
    return None

def _pdm_simulate(machines):
    """Deterministic fallback: return PDM results for all machines."""
    results = []
    for m in machines:
        profile = _PDM_PROFILES.get(m["id"], {"failure_prob": 0.10, "hours_to_failure": 96.0,
                                               "fault_count_7d": 0, "alarm_count_24h": 0,
                                               "action": "OK: No action required."})
        prob  = profile["failure_prob"]
        level = _risk_level(prob)
        feats = _pdm_features_from_machine(m, profile)
        results.append({
            "machine_id":       m["id"],
            "machine_name":     m.get("name", m["id"]),
            "line":             m.get("line", "?"),
            "line_name":        m.get("line_name", ""),
            "state":            m.get("base_state", "running"),
            "failure_prob":     round(prob, 3),
            "risk_level":       level,
            "risk_color":       _risk_color(level),
            "hours_to_failure": profile["hours_to_failure"],
            "recommended_action": profile["action"],
            "features":         feats,
        })
    return sorted(results, key=lambda x: -x["failure_prob"])


@app.route("/api/predict-maintenance")
def predict_maintenance():
    """Run predictive maintenance inference for all machines."""
    machines = _gold_machine_state() or [
        {"id": m["id"], "name": m["name"], "line": m["line"],
         "line_name": m["line_name"], "base_state": m["base_state"],
         "base_oee": m["base_oee"], "base_temp": m["base_temp"]}
        for m in MACHINES_STATIC
    ]

    # Try calling the real PDM endpoint with proba-style payload
    pdm_results = None
    if PDM_ENDPOINT:
        try:
            all_features = []
            for m in machines:
                profile = _PDM_PROFILES.get(m.get("id", ""), {"failure_prob": 0.10,
                    "hours_to_failure": 96.0, "fault_count_7d": 0, "alarm_count_24h": 0, "action": "OK"})
                feats = _pdm_features_from_machine(m, profile)
                all_features.append(feats)
            host, hdrs = _creds()
            payload = {"dataframe_records": all_features}
            r = requests.post(
                f"{host}/serving-endpoints/{PDM_ENDPOINT}/invocations",
                headers=hdrs, json=payload, timeout=12,
            )
            if r.status_code == 200:
                raw_preds = r.json().get("predictions", [])
                pdm_results = []
                for i, m in enumerate(machines):
                    pred = float(raw_preds[i]) if i < len(raw_preds) else 0.1
                    profile = _PDM_PROFILES.get(m.get("id", ""), {"failure_prob": pred,
                        "hours_to_failure": 96.0, "fault_count_7d": 0, "alarm_count_24h": 0, "action": "OK"})
                    level = _risk_level(pred)
                    pdm_results.append({
                        "machine_id":       m.get("id", ""),
                        "machine_name":     m.get("name", m.get("id", "")),
                        "line":             m.get("line", ""),
                        "line_name":        m.get("line_name", ""),
                        "state":            m.get("state", m.get("base_state", "running")),
                        "failure_prob":     round(pred, 3),
                        "risk_level":       level,
                        "risk_color":       _risk_color(level),
                        "hours_to_failure": profile.get("hours_to_failure", 96.0),
                        "recommended_action": profile.get("action", "Monitor."),
                        "features":         all_features[i],
                    })
                pdm_results = sorted(pdm_results, key=lambda x: -x["failure_prob"])
        except Exception:
            pdm_results = None

    if pdm_results is None:
        pdm_results = _pdm_simulate(machines)

    summary = {
        "critical": sum(1 for r in pdm_results if r["risk_level"] == "CRITICAL"),
        "high":     sum(1 for r in pdm_results if r["risk_level"] == "HIGH"),
        "medium":   sum(1 for r in pdm_results if r["risk_level"] == "MEDIUM"),
        "low":      sum(1 for r in pdm_results if r["risk_level"] == "LOW"),
        "model":    PDM_ENDPOINT or "pdm-simulation",
        "uc_table": f"{UC_CATALOG}.mfg_gold.machine_sensor_history",
    }

    return jsonify({"machines": pdm_results, "summary": summary})


# ── PDM top-sensor definitions (used by /api/pdm-timeseries) ─────────────────
_PDM_TOP_SENSORS = {
    "FAL-ASM-01": {"key": "fault_count_7d",          "label": "7-Day Fault Count",     "unit": "faults", "threshold": 4,    "direction": "above", "threshold_label": "Alert Zone"},
    "BDY-WLD-01": {"key": "vibration_rms",            "label": "Vibration RMS",          "unit": "m/s²",   "threshold": 3.5,  "direction": "above", "threshold_label": "Failure Zone"},
    "PNT-ECT-01": {"key": "temp_c",                   "label": "Bath Temperature",       "unit": "°C",     "threshold": 62.0, "direction": "above", "threshold_label": "Overtemp Zone"},
    "PTN-BLD-01": {"key": "spindle_load_pct",         "label": "Spindle Load",           "unit": "%",      "threshold": 85.0, "direction": "above", "threshold_label": "Overload Zone"},
    "BDY-SLD-01": {"key": "cycle_time_deviation_pct", "label": "Cycle Time Deviation",   "unit": "%",      "threshold": 15.0, "direction": "above", "threshold_label": "Failure Zone"},
    "PTN-MCH-01": {"key": "oil_pressure_bar",         "label": "Oil Pressure",           "unit": "bar",    "threshold": 1.8,  "direction": "below", "threshold_label": "Low Pressure Zone"},
    "PTN-DYN-01": {"key": "vibration_rms",            "label": "Vibration RMS",          "unit": "m/s²",   "threshold": 3.5,  "direction": "above", "threshold_label": "Failure Zone"},
    "BDY-STM-01": {"key": "oil_pressure_bar",          "label": "Die Lube Pressure",      "unit": "bar",    "threshold": 1.8,  "direction": "below", "threshold_label": "Low Pressure Zone"},
    "PTN-HAD-01": {"key": "cycle_time_deviation_pct", "label": "Cycle Time Deviation",   "unit": "%",      "threshold": 15.0, "direction": "above", "threshold_label": "Failure Zone"},
    "PNT-PRP-01": {"key": "temp_c",                   "label": "Process Temperature",    "unit": "°C",     "threshold": 62.0, "direction": "above", "threshold_label": "Overtemp Zone"},
    "BDY-INS-01": {"key": "vibration_rms",            "label": "Vibration RMS",          "unit": "m/s²",   "threshold": 3.5,  "direction": "above", "threshold_label": "Failure Zone"},
    "PNT-BSC-01": {"key": "vibration_rms",            "label": "Vibration RMS",          "unit": "m/s²",   "threshold": 3.5,  "direction": "above", "threshold_label": "Failure Zone"},
    "PNT-CLR-01": {"key": "temp_c",                   "label": "Oven Temperature",       "unit": "°C",     "threshold": 195,  "direction": "above", "threshold_label": "Overtemp Zone"},
    "PNT-INS-01": {"key": "vibration_rms",            "label": "Vibration RMS",          "unit": "m/s²",   "threshold": 3.5,  "direction": "above", "threshold_label": "Failure Zone"},
}


@app.route("/api/pdm-timeseries/<machine_id>")
def pdm_timeseries(machine_id):
    """Return 24-hour time-series for the primary failure-driving sensor of a machine."""
    import random as _r, math as _math

    profile     = _PDM_PROFILES.get(machine_id, {"failure_prob": 0.10, "hours_to_failure": 96.0,
                                                   "fault_count_7d": 0, "alarm_count_24h": 0, "action": "OK"})
    sensor_info = _PDM_TOP_SENSORS.get(machine_id, {"key": "vibration_rms", "label": "Vibration RMS",
                                                      "unit": "m/s²", "threshold": 3.5,
                                                      "direction": "above", "threshold_label": "Failure Zone"})
    prob        = profile["failure_prob"]
    threshold   = sensor_info["threshold"]
    direction   = sensor_info["direction"]
    key         = sensor_info["key"]

    seed = int(hashlib.md5(machine_id.encode()).hexdigest()[:4], 16)
    _r.seed(seed)

    # Current value from deterministic feature builder
    m_mock = {"id": machine_id, "base_temp": 40.0 + prob * 30, "base_oee": 60}
    feats  = _pdm_features_from_machine(m_mock, profile)
    current_val = feats[key]

    # Safe baseline 24 h ago
    if direction == "above":
        safe_val = threshold * max(0.3, (1.0 - prob) * 0.85 + (seed / 65535.0) * 0.1)
    else:
        safe_val = threshold * (1.6 + (1.0 - prob) * 0.5 + (seed / 65535.0) * 0.1)

    # Build 24 hourly points (index 0 = 24 h ago, index 23 = now)
    noise_scale = threshold * 0.025
    points = []
    for i in range(24):
        t     = (i / 23.0) ** 1.6          # accelerates toward end
        val   = safe_val + (current_val - safe_val) * t
        val  += (_r.random() - 0.5) * noise_scale * 2
        points.append(round(val, 2))
    points[-1] = round(current_val, 2)      # pin last point exactly

    # Labels: "24h ago" → "Now"
    labels = [f"{23 - i}h ago" if i < 23 else "Now" for i in range(24)]
    labels[22] = "1h ago"

    return jsonify({
        "machine_id":      machine_id,
        "sensor":          key,
        "label":           sensor_info["label"],
        "unit":            sensor_info["unit"],
        "threshold":       threshold,
        "threshold_label": sensor_info["threshold_label"],
        "direction":       direction,
        "risk_level":      _risk_level(prob),
        "risk_color":      _risk_color(_risk_level(prob)),
        "failure_prob":    round(prob, 3),
        "labels":          labels,
        "values":          points,
        "current":         round(current_val, 2),
    })


# ── Equipment Manuals RAG ──────────────────────────────────────────────────────

# Simulated knowledge base used when the live serving endpoint is not configured
_MANUAL_FALLBACK = [
    {
        "q_keywords": ["e-047", "encoder", "fault", "fal-asm"],
        "answer": (
            "Fault E-047 indicates a Transfer Car encoder signal loss on the FAL-ASM-01 station. "
            "Procedure: (1) Power down the transfer car and engage lock-out/tag-out. "
            "(2) Locate the Heidenhain ERN 420 encoder on the drive shaft (see Fig 4-3 in the "
            "Transfer Car Assembly Manual). (3) Inspect the cable connector for fretting or "
            "corrosion — replace M12 connector if continuity test fails. (4) If the encoder "
            "body is damaged, replace with P/N TC-ENC-420-R and torque the coupling to 2.5 Nm. "
            "(5) Run a 10-cycle dry test at 20 % speed before returning to production. "
            "Expected MTTR: 45 minutes."
        ),
        "sources": ["transfer_car_assembly_manual.pdf"],
    },
    {
        "q_keywords": ["oil pressure", "die lube", "bdy-stm", "stamping"],
        "answer": (
            "Low die lubrication pressure on BDY-STM-01 is most commonly caused by a clogged "
            "filter element or a failing pump seal. Procedure: (1) Shut down the 800T Stamping "
            "Press and relieve hydraulic pressure per section 7.2. (2) Replace the 25-micron "
            "lube filter element (P/N STM-LBF-025). (3) Inspect pump output seal; if weeping, "
            "replace with seal kit P/N STM-PSK-800. (4) Bleed the lube circuit and verify "
            "pressure ≥ 2.2 bar at the die inlet before resuming production."
        ),
        "sources": ["800t_stamping_press_manual.pdf"],
    },
    {
        "q_keywords": ["welding", "robot", "fanuc", "r-2000", "maintenance", "pm"],
        "answer": (
            "Scheduled PM for the FANUC R-2000iC welding robot (every 3,840 hours): "
            "(1) Grease all six axes using Mobil Unirex N3 — quantity per axis in Table 5-1. "
            "(2) Check teach pendant cable for kinks; replace if outer jacket is cracked. "
            "(3) Clean TCP (tool centre point) spatter shield and verify TCP calibration. "
            "(4) Inspect wrist unit for oil weepage — acceptable limit < 0.5 g/day. "
            "(5) Test all axis brakes: each axis must hold static load per J7 test spec. "
            "(6) Back up controller parameters to CF card before leaving the cell."
        ),
        "sources": ["fanuc_r2000ic_welding_robot_manual.pdf"],
    },
    {
        "q_keywords": ["e-coat", "electrocoat", "paint", "rectifier", "voltage"],
        "answer": (
            "E-Coat rectifier over-voltage alarm (Code EC-OV): (1) Check bath conductivity — "
            "target 1,200–1,600 µS/cm. High conductivity causes current surge; dilute bath "
            "if above upper limit. (2) Inspect anode bags for rupture; replace any that show "
            "paint contamination. (3) Verify rectifier cooling water flow ≥ 15 L/min. "
            "(4) If alarm persists, reduce ramp rate from 250 V/s to 180 V/s in the PLC "
            "recipe and re-qualify the coating thickness on the next build."
        ),
        "sources": ["e_coat_system_manual.pdf"],
    },
    {
        "q_keywords": ["vision", "inspection", "camera", "false reject", "calibration"],
        "answer": (
            "High false-reject rate on the Vision Inspection System: (1) Clean all eight "
            "camera lenses with IPA wipe — dust is the leading cause of false rejects. "
            "(2) Run the white-balance calibration tile routine (Menu → Calibration → "
            "White Balance) after any lens change. (3) Verify strobe sync pulse is within "
            "±5 µs of trigger; replace strobe controller if drift exceeds this. "
            "(4) If defect-classification confidence is below 92 %, retrain the model "
            "using the last 500 manually verified images."
        ),
        "sources": ["vision_inspection_system_manual.pdf"],
    },
]


def _manual_fallback_answer(question: str) -> dict:
    """Return the best matching simulated answer from the local knowledge base."""
    q_lower = question.lower()
    best_score = 0
    best = _MANUAL_FALLBACK[0]
    for item in _MANUAL_FALLBACK:
        score = sum(1 for kw in item["q_keywords"] if kw in q_lower)
        if score > best_score:
            best_score = score
            best = item
    return {"answer": best["answer"], "sources": best["sources"], "simulated": True}


@app.route("/api/manuals-query", methods=["POST"])
def manuals_query():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    # Try live RAG endpoint if configured
    endpoint_name = MANUALS_ENDPOINT
    try:
        host, hdrs = _creds()
        payload = {"dataframe_records": [{"question": question}]}
        url = f"{host}/serving-endpoints/{endpoint_name}/invocations"
        resp = requests.post(url, headers=hdrs, json=payload, timeout=30)
        if resp.status_code == 200:
            result = resp.json()
            # Handle both direct dict and dataframe_records response formats
            if "predictions" in result:
                pred = result["predictions"]
                if isinstance(pred, list):
                    pred = pred[0]
            else:
                pred = result
            return jsonify({
                "answer":    pred.get("answer", ""),
                "sources":   pred.get("sources", []),
                "simulated": False,
            })
    except Exception:
        pass

    # Fallback to simulated knowledge base
    return jsonify(_manual_fallback_answer(question))


# ── Page Time Logging ───────────────────────────────────────────────────────────
@app.route("/api/log-page-time", methods=["POST"])
def log_page_time():
    data    = request.get_json(silent=True) or {}
    page    = str(data.get("page", ""))[:64]
    seconds = int(data.get("seconds_spent", 0))
    user    = (request.headers.get("X-Forwarded-User")
               or session.get("username", "anonymous"))

    if not _LAKEBASE_OK:
        return jsonify({"status": "skipped", "reason": "no database configured"})

    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO page_time_log (username, page, seconds_spent, app_name) VALUES (%s, %s, %s, %s)",
                    (user, page, seconds, APP_NAME),
                )
            conn.commit()
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"[Lakebase] log_page_time error: {e}", flush=True)
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=8080)
