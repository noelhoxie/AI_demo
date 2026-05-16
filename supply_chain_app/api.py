"""
Databricks Supply Chain Intelligence Platform
Solving: Integrated Business Planning | Inventory & Logistics |
         Precision Demand Forecasting | Order Processing Automation
"""

import math
import os
import random
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

# ── Session secret ─────────────────────────────────────────────────────────────
app.secret_key = os.getenv("SECRET_KEY", os.urandom(32))

# ── Auth config ────────────────────────────────────────────────────────────────
# APP_PASSWORD   — shared password all users enter (required)
# ALLOWED_DOMAINS — comma-separated email domains e.g. "databricks.com,acme.com"
#                   leave blank to allow any email domain
APP_PASSWORD     = os.getenv("APP_PASSWORD", "")   # empty = no auth (Databricks handles it)
# COMPANY_NAME: set explicitly, or falls back to APP_PASSWORD so the
# password itself doubles as the company display name (e.g. APP_PASSWORD=Ernest Packaging)
COMPANY_NAME     = os.getenv("COMPANY_NAME") or APP_PASSWORD
_raw_domains     = os.getenv("ALLOWED_DOMAINS", "")
ALLOWED_DOMAINS  = {d.strip().lower() for d in _raw_domains.split(",") if d.strip()}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if APP_PASSWORD and not session.get("authenticated"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "not authenticated"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

# ── Credentials ────────────────────────────────────────────────────────────────

def _creds():
    raw   = os.environ["DATABRICKS_HOST"].rstrip("/")
    host  = raw if raw.startswith("http") else f"https://{raw}"
    # In Databricks Apps, prefer the calling user's forwarded OAuth token so that
    # personal-workspace resources (Genie spaces, notebooks) are accessible.
    # Fall back to the app service-principal token when outside a request context.
    from flask import has_request_context, request as _req
    user_token = _req.headers.get("X-Forwarded-Access-Token", "") if has_request_context() else ""
    token = user_token or os.environ.get("DATABRICKS_TOKEN", "")
    print(f"[_creds] token_source={'forwarded' if user_token else 'env'} token_prefix={token[:8] if token else 'NONE'}", flush=True)
    hdrs  = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return host, hdrs

GENIE_SPACE_ID = os.getenv("GENIE_SPACE_ID", "")

def _genie_creds():
    """Credentials for Genie API calls using the app service principal."""
    raw  = os.environ["DATABRICKS_HOST"].rstrip("/")
    host = raw if raw.startswith("http") else f"https://{raw}"

    # Databricks Apps injects SP credentials as M2M OAuth (client_id + secret),
    # not as a DATABRICKS_TOKEN PAT. Get a short-lived access token.
    token = os.environ.get("DATABRICKS_TOKEN", "")
    if not token:
        client_id     = os.getenv("DATABRICKS_CLIENT_ID", "")
        client_secret = os.getenv("DATABRICKS_CLIENT_SECRET", "")
        if client_id and client_secret:
            try:
                r = requests.post(
                    f"{host}/oidc/v1/token",
                    data={"grant_type": "client_credentials", "scope": "all-apis"},
                    auth=(client_id, client_secret),
                    timeout=10,
                )
                r.raise_for_status()
                token = r.json().get("access_token", "")
                print(f"[Genie] token_source=M2M_OAUTH prefix={token[:8] if token else 'NONE'}", flush=True)
            except Exception as e:
                print(f"[Genie] M2M token error: {e}", flush=True)
        else:
            print("[Genie] No credentials available (no TOKEN, CLIENT_ID, or CLIENT_SECRET)", flush=True)
    else:
        print(f"[Genie] token_source=DATABRICKS_TOKEN prefix={token[:8]}", flush=True)

    return host, {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
LLM_ENDPOINT            = os.getenv("LLM_ENDPOINT", "databricks-meta-llama-3-3-70b-instruct")
SQL_WAREHOUSE_HTTP_PATH = os.getenv("SQL_WAREHOUSE_HTTP_PATH", "")

# ── Lakebase (Databricks-managed PostgreSQL) ────────────────────────────────────
# Connection uses short-lived OAuth tokens generated from the workspace token.
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
    """Generate a fresh Lakebase credential token via Databricks REST API.

    Works with both PAT auth (DATABRICKS_TOKEN) and OAuth M2M auth
    (DATABRICKS_CLIENT_ID + DATABRICKS_CLIENT_SECRET), which is what
    Databricks Apps injects for the service principal.
    """
    try:
        host         = (os.getenv("LAKEBASE_DATABRICKS_HOST") or os.getenv("DATABRICKS_HOST", "")).rstrip("/")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        pat          = os.getenv("LAKEBASE_DATABRICKS_TOKEN") or os.getenv("DATABRICKS_TOKEN", "")
        client_id    = os.getenv("DATABRICKS_CLIENT_ID", "")
        client_secret= os.getenv("DATABRICKS_CLIENT_SECRET", "")

        if not host:
            print("[Lakebase] DATABRICKS_HOST not set", flush=True)
            return None

        # Resolve bearer token — prefer PAT, fall back to M2M OAuth
        if pat:
            bearer = pat
        elif client_id and client_secret:
            r = requests.post(
                f"{host}/oidc/v1/token",
                data={"grant_type": "client_credentials", "scope": "all-apis"},
                auth=(client_id, client_secret),
                timeout=10,
            )
            r.raise_for_status()
            bearer = r.json()["access_token"]
        else:
            print("[Lakebase] No auth credentials available", flush=True)
            return None

        # Call Databricks REST API to generate a Lakebase DB credential
        r = requests.post(
            f"{host}/api/2.0/postgres/credentials",
            headers={"Authorization": f"Bearer {bearer}"},
            json={"endpoint": LAKEBASE_ENDPOINT},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("token")
    except Exception as e:
        print(f"[Lakebase] Token generation failed: {e}", flush=True)
        return None

def _db_connect():
    tok = _lakebase_token()
    if not tok:
        raise RuntimeError("Could not obtain Lakebase token")
    return psycopg2.connect(
        host=LAKEBASE_HOST,
        port=LAKEBASE_PORT,
        dbname=LAKEBASE_DB,
        user=LAKEBASE_USER,
        password=tok,
        sslmode="require",
        connect_timeout=10,
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
                # Migrate existing table — add app_name if not present
                cur.execute("""
                    ALTER TABLE page_time_log
                    ADD COLUMN IF NOT EXISTS app_name TEXT
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS contact_submissions (
                        id           SERIAL PRIMARY KEY,
                        name         TEXT,
                        company      TEXT,
                        email        TEXT,
                        role         TEXT,
                        interest     TEXT,
                        message      TEXT,
                        submitted_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
            conn.commit()
        print("[Lakebase] tables ready")
    except Exception as e:
        print(f"[Lakebase] Could not create tables: {e}")

_ensure_page_log_table()

# ── Daily-consistent data seed ──────────────────────────────────────────────────
_DAY_SEED = int(time.time() / 86400)
_rng = random.Random(_DAY_SEED)

def _j(base, pct=0.02):
    """Apply a small daily jitter so numbers feel live but stay consistent."""
    return base * (1 + (_rng.random() - 0.5) * pct * 2)

# ── Auth Routes ─────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username     = (request.form.get("username") or "").strip()
        company_name = (request.form.get("password") or "").strip()

        if username and company_name:
            session["authenticated"]  = True
            session["username"]        = username
            session["company_name"]    = company_name
            return redirect("/portal")
        else:
            error = "Please enter your name and company to continue."

    return send_from_directory("static", "login.html"), 200 if not error else 401

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/portal")
@login_required
def portal():
    return send_from_directory("static", "portal.html")

@app.route("/api/config")
@login_required
def config():
    apps = [
        {
            "name":     os.getenv("APP_1_NAME", "Supply Chain Intelligence"),
            "tagline":  os.getenv("APP_1_TAGLINE", "IBP · Inventory · Demand · Orders"),
            "desc":     os.getenv("APP_1_DESC",  "End-to-end supply chain visibility — integrated business planning, inventory optimisation, AI demand forecasting, and order automation in one platform."),
            "url":      os.getenv("APP_1_URL",   "/"),
            "features": os.getenv("APP_1_FEATURES", "Integrated Business Planning,Inventory & Logistics,Demand Forecasting AI,Order Automation").split(","),
            "badge":    os.getenv("APP_1_BADGE", "Supply Chain"),
            "color":    os.getenv("APP_1_COLOR", "#1B6FEB"),
        },
        {
            "name":     os.getenv("APP_2_NAME", "SKU Rationalization"),
            "tagline":  os.getenv("APP_2_TAGLINE", "Cluster · Score · Retire · Commit"),
            "desc":     os.getenv("APP_2_DESC",  "Identify and retire near-duplicate SKUs in SAP. Four-stage Databricks pipeline with human-in-the-loop review and SAP change-request output."),
            "url":      os.getenv("APP_2_URL",   ""),
            "features": os.getenv("APP_2_FEATURES", "Dimensional Clustering,Confidence Scoring,Match Rules Engine,SAP Change Requests").split(","),
            "badge":    os.getenv("APP_2_BADGE", "Manufacturing"),
            "color":    os.getenv("APP_2_COLOR", "#10b981"),
        },
        {
            "name":     os.getenv("APP_3_NAME", "Coming Soon"),
            "tagline":  os.getenv("APP_3_TAGLINE", ""),
            "desc":     os.getenv("APP_3_DESC",  "A third Databricks-powered application will appear here. Set APP_3_NAME, APP_3_URL, and APP_3_DESC in your environment variables."),
            "url":      os.getenv("APP_3_URL",   ""),
            "features": os.getenv("APP_3_FEATURES", "").split(",") if os.getenv("APP_3_FEATURES") else [],
            "badge":    os.getenv("APP_3_BADGE", ""),
            "color":    os.getenv("APP_3_COLOR", "#8b5cf6"),
        },
    ]
    return jsonify({
        "company_name": session.get("company_name", COMPANY_NAME),
        "username":     session.get("username", ""),
        "apps":         apps,
    })

@app.route("/api/contact", methods=["POST"])
@login_required
def contact():
    data    = request.get_json(silent=True) or {}
    name    = str(data.get("name",     ""))[:120]
    company = str(data.get("company",  ""))[:120]
    email   = str(data.get("email",    session.get("email", "")))[:120]
    role    = str(data.get("role",     ""))[:120]
    interest= str(data.get("interest", ""))[:120]
    message = str(data.get("message",  ""))[:1000]

    if not _LAKEBASE_OK:
        print(f"[Contact] (no DB) name={name} company={company} email={email} role={role} interest={interest}")
        return jsonify({"status": "ok", "stored": False})

    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO contact_submissions
                       (name, company, email, role, interest, message)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (name, company, email, role, interest, message),
                )
            conn.commit()
        print(f"[Contact] saved name={name} email={email}")
        return jsonify({"status": "ok", "stored": True})
    except Exception as e:
        print(f"[Contact] DB error (submission logged above): {e}")
        # Still return 200 — the submission was captured in logs even if DB write failed
        return jsonify({"status": "ok", "stored": False, "note": "logged only"})

# ── Static Routes ───────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return send_from_directory("static", "index.html")

@app.route("/static/<path:path>")
def static_files(path):
    return send_from_directory("static", path)

# ── Time constants ──────────────────────────────────────────────────────────────

_MONTHS_HIST = [
    "Jun-24", "Jul-24", "Aug-24", "Sep-24", "Oct-24", "Nov-24",
    "Dec-24", "Jan-25", "Feb-25", "Mar-25", "Apr-25", "May-25",
]
_MONTHS_FWD = ["Jun-25", "Jul-25", "Aug-25", "Sep-25", "Oct-25", "Nov-25"]
_ALL_MONTHS = _MONTHS_HIST + _MONTHS_FWD

# ── /api/kpis ───────────────────────────────────────────────────────────────────

@app.route("/api/kpis")
@login_required
def kpis():
    return jsonify({
        "plan_attainment":   round(_j(91.4), 1),
        "inventory_turns":   round(_j(8.4),  1),
        "forecast_mape":     round(_j(9.1),  1),
        "order_automation":  round(_j(78.4), 1),
        "on_time_delivery":  round(_j(91.3), 1),
        "fill_rate":         round(_j(97.2), 1),
        "excess_value_m":    round(_j(12.4), 1),
        "open_exceptions":   47,
    })

# ── /api/ibp ────────────────────────────────────────────────────────────────────

@app.route("/api/ibp")
@login_required
def ibp():
    rng = random.Random(_DAY_SEED + 1)

    # 18-month consensus / financial / capacity plan
    # Seasonal factors by month — no linear trend; each month is independently driven
    _seasonal = {
        'Jan': 0.84, 'Feb': 0.87, 'Mar': 0.93, 'Apr': 0.97,
        'May': 1.00, 'Jun': 0.96, 'Jul': 0.91, 'Aug': 0.95,
        'Sep': 1.01, 'Oct': 1.06, 'Nov': 1.09, 'Dec': 1.13,
    }
    plan_data = []
    base = 138.0
    asp_m = 0.00045  # $450 ASP → $0.00045M per unit; divide $M by asp_m to get K units
    for i, m in enumerate(_ALL_MONTHS):
        seasonal   = _seasonal.get(m[:3], 1.0)
        consensus  = round(_j(base * seasonal) * (1 + (rng.random() - 0.5) * 0.04), 1)
        financial  = round(consensus  * (1 + rng.random() * 0.04),                    1)
        capacity   = round(financial  * (1.05 + rng.random() * 0.02),                 1)
        plan_data.append({
            "month":       m,
            "consensus":   consensus,
            "financial":   financial,
            "capacity":    capacity,
            "consensus_k": round(consensus / asp_m / 1000),
            "financial_k": round(financial / asp_m / 1000),
            "capacity_k":  round(capacity  / asp_m / 1000),
            "is_future":   m in _MONTHS_FWD,
        })

    # S&OP pipeline stages
    sop_stages = [
        {"stage": "Data Collection",       "status": "complete",     "owner": "Finance & Ops",  "date": "Apr 28"},
        {"stage": "Statistical Forecast",  "status": "complete",     "owner": "Demand Planning","date": "Apr 30"},
        {"stage": "Unconstrained Demand",  "status": "complete",     "owner": "Commercial",     "date": "May 2"},
        {"stage": "Supply Review",         "status": "in_progress",  "owner": "Supply Chain",   "date": "May 7"},
        {"stage": "Consensus Meeting",     "status": "pending",      "owner": "S&OP Team",      "date": "May 12"},
        {"stage": "Executive Sign-off",    "status": "pending",      "owner": "Leadership",     "date": "May 14"},
    ]

    # BU attainment
    bus = [
        {"bu": "North America",  "attainment": round(_j(94.2), 1), "target": 95.0},
        {"bu": "EMEA",           "attainment": round(_j(88.7), 1), "target": 92.0},
        {"bu": "APAC",           "attainment": round(_j(91.3), 1), "target": 90.0},
        {"bu": "Latin America",  "attainment": round(_j(86.1), 1), "target": 88.0},
        {"bu": "Rest of World",  "attainment": round(_j(79.4), 1), "target": 85.0},
    ]

    # Risk register
    risks = [
        {"item": "EMEA capacity shortfall Q3",                   "impact": "High",   "value_m": 4.2, "owner": "S. Kowalski"},
        {"item": "Asia-Pac port congestion — inbound delay +3wk","impact": "High",   "value_m": 2.8, "owner": "T. Nguyen"},
        {"item": "Key component lead time extended +4 weeks",    "impact": "Medium", "value_m": 1.9, "owner": "R. Patel"},
        {"item": "Q4 demand spike not captured in consensus",    "impact": "Medium", "value_m": 3.1, "owner": "M. Chen"},
        {"item": "New product launch timing uncertainty",        "impact": "Low",    "value_m": 0.7, "owner": "A. Davies"},
    ]

    return jsonify({
        "plan_data":    plan_data,
        "sop_stages":   sop_stages,
        "bu_attainment": bus,
        "risks":        risks,
        "kpis": {
            "plan_attainment":  round(_j(91.4), 1),
            "forecast_accuracy": round(_j(87.3), 1),
            "consensus_rate":   round(_j(94.1), 1),
            "cycle_days":       14,
        },
    })

# ── /api/inventory ──────────────────────────────────────────────────────────────

@app.route("/api/inventory")
@login_required
def inventory():
    warehouses = [
        {"name": "Chicago DC",   "code": "ORD", "utilization": round(_j(87), 1), "skus": 1842, "dos": round(_j(32), 1), "region": "North America"},
        {"name": "Dallas DC",    "code": "DFW", "utilization": round(_j(74), 1), "skus": 1421, "dos": round(_j(28), 1), "region": "North America"},
        {"name": "Rotterdam DC", "code": "RTM", "utilization": round(_j(91), 1), "skus": 2103, "dos": round(_j(41), 1), "region": "EMEA"},
        {"name": "Singapore DC", "code": "SIN", "utilization": round(_j(68), 1), "skus": 1654, "dos": round(_j(24), 1), "region": "APAC"},
        {"name": "Monterrey DC", "code": "MTY", "utilization": round(_j(82), 1), "skus":  987, "dos": round(_j(36), 1), "region": "Latin America"},
    ]

    categories = [
        {"name": "Finished Goods",  "dos": round(_j(38), 1), "lo": 25, "hi": 45, "value_m": 48.2},
        {"name": "Work in Progress","dos": round(_j(12), 1), "lo":  8, "hi": 18, "value_m": 22.7},
        {"name": "Raw Materials",   "dos": round(_j(52), 1), "lo": 30, "hi": 60, "value_m": 31.4},
        {"name": "Packaging",       "dos": round(_j(67), 1), "lo": 30, "hi": 60, "value_m":  8.1},
        {"name": "MRO",             "dos": round(_j(91), 1), "lo": 45, "hi": 90, "value_m":  5.3},
    ]

    health = {"optimal": 4823, "excess": 891, "at_risk": 412, "stockout": 121}

    alerts = [
        {"sku": "FG-78421", "desc": "Premium Sprocket Assembly",  "dos": 187, "value_k": 284, "location": "Chicago DC",   "type": "excess"},
        {"sku": "RM-34892", "desc": "Alloy Steel Rod 25mm",       "dos": 143, "value_k": 142, "location": "Rotterdam DC", "type": "excess"},
        {"sku": "FG-91033", "desc": "Drive Belt Assembly XL",     "dos":   3, "value_k":  67, "location": "Singapore DC", "type": "stockout"},
        {"sku": "PKG-2201", "desc": "Corrugated Box 48×36",       "dos": 128, "value_k":  38, "location": "Dallas DC",    "type": "excess"},
        {"sku": "FG-55102", "desc": "Hydraulic Pump Unit",        "dos":   4, "value_k": 421, "location": "Chicago DC",   "type": "stockout"},
        {"sku": "WIP-7742", "desc": "Sub-Assembly Module B",      "dos":   6, "value_k":  93, "location": "Monterrey DC", "type": "at_risk"},
    ]

    return jsonify({
        "warehouses":  warehouses,
        "categories":  categories,
        "health":      health,
        "alerts":      alerts,
        "kpis": {
            "inventory_turns": round(_j(8.4),  1),
            "days_on_hand":    round(_j(43),   1),
            "fill_rate":       round(_j(97.2), 1),
            "excess_value_m":  round(_j(12.4), 1),
        },
    })

# ── /api/demand ─────────────────────────────────────────────────────────────────

@app.route("/api/demand")
@login_required
def demand():
    rng = random.Random(_DAY_SEED + 3)
    base = 144_000

    _over_reasons = [
        "Planned promotional uplift did not materialise — retailer pulled forward volume to the prior period.",
        "Customer order consolidation shifted demand to Q+1; two large accounts delayed releases.",
        "New product launch cannibalized existing SKU volumes faster than the model anticipated.",
        "EMEA industrial demand softer than modelled — energy cost headwinds reduced customer run rates.",
        "Sales pipeline conversion rate dropped; three key opportunities pushed to the following month.",
        "Logistics disruption caused a shipment timing shift — demand was fulfilled in an adjacent period.",
    ]
    _under_reasons = [
        "Competitor supply disruption drove an unexpected surge — three new accounts won mid-month.",
        "Promotional campaign outperformed plan by 18%; higher-than-forecast retailer pull-through.",
        "Q-end customer stocking behaviour — multiple accounts accelerated orders ahead of a price increase.",
        "New product fill orders exceeded expectations; initial channel inventory build was 22% above forecast.",
        "Unmodelled incremental export volume from an APAC distributor placed a large spot order.",
        "Seasonal demand arrived three weeks earlier than the historical pattern, pulling volume from next month.",
    ]
    _flat_reasons = [
        "Forecast was within normal variance; model performance within ±3% for the period.",
        "Demand planners applied a small upward override that proved accurate for this month.",
        "Statistical model captured seasonal pattern well; no significant demand events this period.",
    ]

    fa_data = []
    for i, m in enumerate(_MONTHS_HIST):
        trend  = 1 + i * 0.008
        actual = round(_j(base * trend, 0.04))
        fc     = round(actual * (1 + (rng.random() - 0.5) * 0.1))
        bias   = (fc - actual) / actual * 100
        if bias > 3:
            reason = _over_reasons[i % len(_over_reasons)]
        elif bias < -3:
            reason = _under_reasons[i % len(_under_reasons)]
        else:
            reason = _flat_reasons[i % len(_flat_reasons)]
        fa_data.append({"month": m, "forecast": fc, "actual": actual, "reason": reason})

    cat_mape = [
        {"category": "Finished Goods",  "mape": round(_j(8.2),  1), "bias": round(_j(-1.4, 0.3), 1), "skus": 1842},
        {"category": "Components",      "mape": round(_j(11.4), 1), "bias": round(_j(-3.2, 0.3), 1), "skus": 2401},
        {"category": "Raw Materials",   "mape": round(_j(14.7), 1), "bias": round(_j( 2.1, 0.3), 1), "skus":  842},
        {"category": "Packaging",       "mape": round(_j(7.8),  1), "bias": round(_j(-0.8, 0.3), 1), "skus":  963},
        {"category": "MRO",             "mape": round(_j(22.1), 1), "bias": round(_j( 5.3, 0.3), 1), "skus":  200},
    ]

    # Per-SKU base actuals and bias offsets for 12-month history
    _sku_defs = [
        {"sku": "FG-55102", "desc": "Hydraulic Pump Unit",       "mape": 34.2, "bias": -28.1, "last_actual":  842,
         "base":  820, "vol": 0.06, "bias_pct": -0.28, "trend":  0.010},
        {"sku": "FG-78421", "desc": "Premium Sprocket Assembly", "mape": 28.7, "bias":  22.4, "last_actual": 1204,
         "base": 1150, "vol": 0.05, "bias_pct":  0.22, "trend":  0.006},
        {"sku": "CP-33901", "desc": "Control Module Type C",     "mape": 24.1, "bias": -19.8, "last_actual": 3401,
         "base": 3200, "vol": 0.04, "bias_pct": -0.19, "trend":  0.008},
        {"sku": "RM-44211", "desc": "Titanium Sheet 2mm",        "mape": 21.8, "bias":  18.2, "last_actual":  621,
         "base":  600, "vol": 0.05, "bias_pct":  0.18, "trend":  0.005},
        {"sku": "FG-91033", "desc": "Drive Belt Assembly XL",    "mape": 19.4, "bias": -16.7, "last_actual": 2804,
         "base": 2650, "vol": 0.04, "bias_pct": -0.16, "trend":  0.009},
    ]
    sku_rng = random.Random(_DAY_SEED + 7)
    top_errors = []
    for sd in _sku_defs:
        history = []
        for i, m in enumerate(_MONTHS_HIST):
            actual = round(sd["base"] * (1 + i * sd["trend"]) * (1 + (sku_rng.random() - 0.5) * sd["vol"]))
            fc     = round(actual * (1 + sd["bias_pct"] + (sku_rng.random() - 0.5) * 0.06))
            history.append({"month": m, "forecast": fc, "actual": actual})
        top_errors.append({
            "sku": sd["sku"], "desc": sd["desc"],
            "mape": sd["mape"], "bias": sd["bias"],
            "last_actual": sd["last_actual"],
            "history": history,
        })

    # MAPE improving trend
    mape_trend = []
    for i, m in enumerate(_MONTHS_HIST):
        mape_trend.append({"month": m, "mape": round(_j(9.1 + (5 - i) * 0.42, 0.04), 1)})

    return jsonify({
        "forecast_vs_actual": fa_data,
        "category_mape":      cat_mape,
        "top_errors":         top_errors,
        "mape_trend":         mape_trend,
        "kpis": {
            "mape":               round(_j(9.1),  1),
            "bias":               round(_j(-2.3, 0.1), 1),
            "forecast_value_add": round(_j(12.4), 1),
            "skus_forecast":      6248,
        },
    })

# ── /api/orders ─────────────────────────────────────────────────────────────────

@app.route("/api/orders")
@login_required
def orders():
    exceptions = [
        {
            "type": "Price Discrepancy", "count": 23, "aging_days": round(_j(4.2), 1),
            "value_k": 184, "priority": "high",
            "root_cause": "18 of 23 POs are from Pacific Components where the Q2 contract renewal has not been loaded into ERP — system is applying the expired Q1 rate card. The remaining 5 relate to EUR/USD FX rate mismatches on European supplier invoices.",
            "recommendations": [
                {"action": "Load renewed Pacific Components rate card into ERP contract master (Item: PSUP-CONTRACT-2024-Q2). This resolves 18 POs and releases $143K automatically.", "type": "auto", "impact": "High"},
                {"action": "Run FX rate refresh job for EUR-denominated POs. Three Precision Parts GmbH POs will auto-resolve once the daily FX feed is applied.", "type": "auto", "impact": "Medium"},
                {"action": "Escalate 2 remaining POs (PO-84421, PO-84438) to the procurement manager — supplier is disputing the agreed unit price for SKU-CP-301.", "type": "manual", "impact": "Low"},
            ],
            "pos": [
                {"po": "PO-84401", "supplier": "Pacific Components",    "material": "Control Module Type C",     "value_k": 12.4, "age_days": 5, "issue": "Contract rate gap — ERP applying Q1 price $41.20 vs agreed Q2 price $38.50"},
                {"po": "PO-84403", "supplier": "Pacific Components",    "material": "Sensor Array C",            "value_k":  9.8, "age_days": 4, "issue": "Contract rate gap — ERP applying Q1 price $41.20 vs agreed Q2 price $38.50"},
                {"po": "PO-84408", "supplier": "Pacific Components",    "material": "Drive Unit D",              "value_k": 18.2, "age_days": 6, "issue": "Contract rate gap — ERP applying Q1 price $41.20 vs agreed Q2 price $38.50"},
                {"po": "PO-84415", "supplier": "Pacific Components",    "material": "PCB Module G",              "value_k":  7.1, "age_days": 3, "issue": "Contract rate gap — Q2 rate card not loaded"},
                {"po": "PO-84421", "supplier": "Pacific Components",    "material": "Cable Harness J",           "value_k":  5.3, "age_days": 7, "issue": "Disputed unit price — supplier invoice $71.50 vs PO $68.00; under negotiation"},
                {"po": "PO-84429", "supplier": "Precision Parts GmbH", "material": "Hydraulic Valve B",         "value_k": 14.6, "age_days": 2, "issue": "EUR/USD FX mismatch — invoice converted at 1.072, PO created at 1.089"},
                {"po": "PO-84433", "supplier": "Precision Parts GmbH", "material": "Bearing Kit E",             "value_k":  8.9, "age_days": 2, "issue": "EUR/USD FX mismatch — daily FX feed not yet applied to this PO"},
            ],
        },
        {
            "type": "Delivery Date Mismatch", "count": 11, "aging_days": round(_j(2.8), 1),
            "value_k": 92, "priority": "medium",
            "root_cause": "Suppliers confirmed ETDs 4–12 days later than PO-required delivery dates. 4 POs from Acero del Norte are delayed due to a Mexican customs hold. 3 EuroTech POs are affected by a Rotterdam port backlog. The remaining 4 have supplier capacity constraints.",
            "recommendations": [
                {"action": "Contact Acero del Norte logistics coordinator (Maria Santos) to confirm updated ETD for PO-91201 through PO-91204. Request ASN update in portal by EOD.", "type": "manual", "impact": "High"},
                {"action": "Notify production scheduling of 4 impacted material receipts. Assess whether safety stock can cover the gap — current DOS on affected SKUs is 18 days.", "type": "manual", "impact": "High"},
                {"action": "For EuroTech POs, switch carrier from sea to air freight for PO-91208 (Pump Assembly F, $31K). Air premium ~$2.1K vs $14K stockout risk.", "type": "auto", "impact": "Medium"},
                {"action": "Enable ERP alert rule: flag any supplier ASN that deviates >3 days from PO delivery date within 24 hours of ASN submission.", "type": "auto", "impact": "Medium"},
            ],
            "pos": [
                {"po": "PO-91201", "supplier": "Acero del Norte",    "material": "Frame Component H",  "value_k": 18.7, "age_days": 3, "issue": "Customs hold at Monterrey port — new ETD May 19 vs PO req May 14"},
                {"po": "PO-91202", "supplier": "Acero del Norte",    "material": "Bearing Kit E",      "value_k":  6.2, "age_days": 3, "issue": "Customs hold — same shipment as PO-91201"},
                {"po": "PO-91203", "supplier": "Acero del Norte",    "material": "Seal Kit I",         "value_k":  4.1, "age_days": 2, "issue": "Customs hold — awaiting broker clearance"},
                {"po": "PO-91204", "supplier": "Acero del Norte",    "material": "Motor Unit K",       "value_k": 11.3, "age_days": 4, "issue": "Supplier capacity constraint — delayed to May 22"},
                {"po": "PO-91207", "supplier": "EuroTech Supplies",  "material": "Pump Assembly F",    "value_k": 31.4, "age_days": 2, "issue": "Rotterdam port backlog — vessel delayed 6 days"},
                {"po": "PO-91208", "supplier": "EuroTech Supplies",  "material": "Filter Assembly L",  "value_k":  9.8, "age_days": 2, "issue": "Rotterdam port backlog — same vessel delay"},
                {"po": "PO-91211", "supplier": "Allied Materials",   "material": "Actuator M",         "value_k": 10.5, "age_days": 1, "issue": "Supplier capacity constraint — production line maintenance pushed ETD 4 days"},
            ],
        },
        {
            "type": "Missing PO Reference", "count": 7, "aging_days": round(_j(6.1), 1),
            "value_k": 41, "priority": "high",
            "root_cause": "4 POs were created via the legacy procurement portal during last month's ERP migration window and were not assigned system PO numbers. 3 POs are from a newly onboarded supplier (Nordic Components) whose EDI connection was not yet live when orders were placed.",
            "recommendations": [
                {"action": "Run ERP auto-assignment script for the 4 migration-window POs (PO-MIGR-001 through 004). Script maps purchase requisition numbers to PO records — estimated 15 min runtime.", "type": "auto", "impact": "High"},
                {"action": "Manually assign PO references for 3 Nordic Components POs by cross-referencing the purchase requisition log. Assign PO-NC-2024-001 through 003 and notify supplier.", "type": "manual", "impact": "Medium"},
                {"action": "Activate Nordic Components EDI connection (IT ticket #IT-4421 is open). Once live, all future orders will auto-assign PO numbers at creation.", "type": "manual", "impact": "Medium"},
                {"action": "Add ERP validation rule: block PO creation without a system-assigned PO number — force requisition reference at order entry.", "type": "auto", "impact": "Low"},
            ],
            "pos": [
                {"po": "PO-MIGR-001", "supplier": "Apex Industrial",      "material": "Control Module A",    "value_k":  8.4, "age_days": 7, "issue": "Created via legacy portal during ERP migration — no system PO number assigned"},
                {"po": "PO-MIGR-002", "supplier": "Apex Industrial",      "material": "Sensor Array C",     "value_k":  6.1, "age_days": 7, "issue": "Created via legacy portal during ERP migration — no system PO number assigned"},
                {"po": "PO-MIGR-003", "supplier": "CoreMaterials",        "material": "Hydraulic Valve B",  "value_k":  4.9, "age_days": 6, "issue": "Legacy portal migration artifact — requisition ref PR-44201 not linked"},
                {"po": "PO-MIGR-004", "supplier": "CoreMaterials",        "material": "Seal Kit I",         "value_k":  3.2, "age_days": 6, "issue": "Legacy portal migration artifact"},
                {"po": "PO-NC-001",   "supplier": "Nordic Components",    "material": "PCB Module G",       "value_k":  7.8, "age_days": 5, "issue": "New supplier — EDI not live at order creation, no auto PO reference"},
                {"po": "PO-NC-002",   "supplier": "Nordic Components",    "material": "Display Panel N",    "value_k":  6.4, "age_days": 5, "issue": "New supplier — EDI connection pending IT ticket #IT-4421"},
                {"po": "PO-NC-003",   "supplier": "Nordic Components",    "material": "Cable Harness J",    "value_k":  4.2, "age_days": 4, "issue": "New supplier — manual order placed, reference not assigned"},
            ],
        },
        {
            "type": "Quantity Variance >5%",  "count": 4, "aging_days": round(_j(3.4), 1),
            "value_k": 218, "priority": "medium",
            "root_cause": "All 4 POs involve short shipments from Pacific Components. Received quantities are 8–22% below PO quantities. Root cause is a raw material allocation constraint at the supplier's Shenzhen facility — they allocated available inventory across multiple customers rather than fulfilling any single PO in full.",
            "recommendations": [
                {"action": "Accept partial receipts and close the receipt line for goods already received. Raise a new expedite PO for the shortfall quantities with a 10-day lead time commitment from Pacific Components.", "type": "manual", "impact": "High"},
                {"action": "Review safety stock levels for the 3 affected SKUs. Current DOS on SKU-CP-301 is 6 days — below the 7-day at-risk threshold. Trigger an emergency replenishment order.", "type": "auto", "impact": "High"},
                {"action": "Escalate Pacific Components supply constraint to VP Procurement. Request allocation priority commitment for Q2 remaining volume given $11.7M annual spend relationship.", "type": "manual", "impact": "Medium"},
                {"action": "Dual-source SKU-CP-301 and SKU-DA-410 as backup suppliers to eliminate single-source dependency. RFQ to 2 alternative suppliers in 48 hours.", "type": "manual", "impact": "Low"},
            ],
            "pos": [
                {"po": "PO-77301", "supplier": "Pacific Components", "material": "Drive Unit D",         "value_k": 82.5, "age_days": 4, "issue": "Short shipment — ordered 250 units, received 195 (22% short). Supplier allocation constraint."},
                {"po": "PO-77308", "supplier": "Pacific Components", "material": "Control Module A",     "value_k": 68.4, "age_days": 3, "issue": "Short shipment — ordered 480 units, received 432 (10% short)."},
                {"po": "PO-77315", "supplier": "Pacific Components", "material": "Sensor Array C",       "value_k": 42.1, "age_days": 3, "issue": "Short shipment — ordered 200 units, received 164 (18% short). SKU at-risk DOS."},
                {"po": "PO-77322", "supplier": "Pacific Components", "material": "Motor Unit K",         "value_k": 25.0, "age_days": 2, "issue": "Short shipment — ordered 60 units, received 55 (8% short)."},
            ],
        },
        {
            "type": "Unmatched Invoice", "count": 2, "aging_days": round(_j(8.7), 1),
            "value_k": 67, "priority": "high",
            "root_cause": "Invoice INV-AP-8841 arrived before the goods receipt was posted in ERP — the 3-way match cannot complete until the receipt is confirmed. Invoice INV-AP-8857 has a PO number typo (PO-84O33 instead of PO-84033) which broke the automated matching rule.",
            "recommendations": [
                {"action": "Post goods receipt for PO-84029 in ERP (goods are in warehouse, receipt not yet confirmed by warehouse staff). This unblocks INV-AP-8841 for 3-way match automatically.", "type": "manual", "impact": "High"},
                {"action": "Correct PO reference on INV-AP-8857 from PO-84O33 to PO-84033 (letter O vs digit 0). Resubmit through AP matching workflow — will auto-clear.", "type": "auto", "impact": "High"},
                {"action": "Add OCR validation rule in AP inbox to flag PO numbers containing letter O adjacent to digits — catches this class of typo at invoice ingestion.", "type": "auto", "impact": "Medium"},
            ],
            "pos": [
                {"po": "PO-84029", "supplier": "Allied Materials",     "material": "Actuator M",          "value_k": 38.0, "age_days": 9, "issue": "Invoice INV-AP-8841 received before goods receipt posted. Goods in WH-01, receipt pending warehouse confirmation."},
                {"po": "PO-84033", "supplier": "Europart GmbH",        "material": "Pump Assembly F",     "value_k": 29.0, "age_days": 8, "issue": "Invoice INV-AP-8857 has PO reference typo — 'PO-84O33' (letter O) vs correct 'PO-84033' (digit 0). Auto-match failed."},
            ],
        },
    ]

    suppliers = [
        {"name": "Apex Industrial",       "otd": round(_j(96.4), 1), "pos": 142, "spend_m": 8.4,  "country": "USA"},
        {"name": "Precision Parts GmbH",  "otd": round(_j(91.8), 1), "pos":  89, "spend_m": 6.2,  "country": "Germany"},
        {"name": "Pacific Components",    "otd": round(_j(88.2), 1), "pos": 203, "spend_m": 11.7, "country": "China"},
        {"name": "Acero del Norte",       "otd": round(_j(84.7), 1), "pos":  67, "spend_m": 4.1,  "country": "Mexico"},
        {"name": "Allied Materials",      "otd": round(_j(93.1), 1), "pos": 118, "spend_m": 7.8,  "country": "USA"},
        {"name": "EuroTech Supplies",     "otd": round(_j(79.3), 1), "pos":  54, "spend_m": 3.2,  "country": "Netherlands"},
    ]

    order_vol = []
    for i, m in enumerate(_MONTHS_HIST):
        total = round(_j(2840 + i * 40, 0.04))
        auto  = round(total * _j(0.784, 0.03))
        order_vol.append({"month": m, "total": total, "automated": auto, "manual": total - auto})

    # Automation rate trend
    auto_trend = []
    for i, m in enumerate(_MONTHS_HIST):
        auto_trend.append({"month": m, "rate": round(_j(78.4 - (11 - i) * 0.7, 0.02), 1)})

    return jsonify({
        "exceptions":      exceptions,
        "suppliers":       suppliers,
        "order_volume":    order_vol,
        "automation_trend": auto_trend,
        "kpis": {
            "automation_rate": round(_j(78.4), 1),
            "avg_cycle_hours": round(_j(4.2),  1),
            "exceptions_open": 47,
            "on_time_delivery": round(_j(91.3), 1),
        },
    })

# ── /api/ai-chat ────────────────────────────────────────────────────────────────

_FALLBACK_RESPONSES = [
    {
        "keywords": ["ibp", "plan", "s&op", "consensus", "attainment"],
        "answer": (
            "The current S&OP cycle shows plan attainment at **91.4%** against a 95% target. "
            "The key gap is in EMEA (88.7%) driven by a Q3 capacity shortfall worth $4.2M. "
            "The consensus meeting is gated for May 12th — I recommend escalating the EMEA "
            "capacity issue before that stage. Resolving it alone would move overall attainment "
            "to approximately **93.1%** and recover 2.8 weeks of supply buffer."
        ),
        "follow_ups": [
            "What is the financial impact of the EMEA capacity gap?",
            "Which BU is furthest from plan attainment target?",
            "When is the next S&OP executive sign-off?",
        ],
    },
    {
        "keywords": ["inventory", "stock", "dos", "excess", "stockout", "warehouse"],
        "answer": (
            "Current inventory health: **121 stockouts** and **$12.4M in excess stock**. "
            "The most critical stockout is FG-55102 (Hydraulic Pump Unit) at 4 days of supply "
            "in Chicago DC — already impacting the Apex Industrial order schedule. Rotterdam DC "
            "is at 91% utilization. A lateral transfer of 200 units of FG-78421 from Chicago "
            "would relieve Rotterdam and recover $284K of excess in a single move."
        ),
        "follow_ups": [
            "Which DCs are at capacity risk this quarter?",
            "What is the total value of excess inventory?",
            "Show me all stockout SKUs in APAC.",
        ],
    },
    {
        "keywords": ["forecast", "demand", "mape", "bias", "accuracy"],
        "answer": (
            "Overall MAPE is **9.1%** — just inside the 10% target. MRO is the outlier at 22.1% "
            "and should be reviewed. A systematic under-forecast bias of **-2.3%** across Finished "
            "Goods means you are consistently running leaner than planned. FG-55102 has the highest "
            "error at 34.2% MAPE, which is directly correlated with the stockout position on that SKU."
        ),
        "follow_ups": [
            "What is driving the MRO forecast error?",
            "Which SKUs improved the most in MAPE last quarter?",
            "How does our bias compare to industry benchmark?",
        ],
    },
    {
        "keywords": ["order", "po", "purchase", "automation", "exception", "supplier"],
        "answer": (
            "Order automation is running at **78.4%**, up from 71.2% six months ago. "
            "The **23 price discrepancy exceptions** represent $184K in held orders — 18 are from "
            "Pacific Components where a contract renewal is pending. Resolving that contract "
            "would auto-clear 78% of the exception queue and push the automation rate above **82%**."
        ),
        "follow_ups": [
            "Which supplier has the worst on-time delivery?",
            "What is the average age of open exceptions?",
            "How much revenue is blocked by open exceptions?",
        ],
    },
]

_DEFAULT_RESPONSE = {
    "answer": (
        "Based on your current supply chain data: plan attainment is **91.4%**, "
        "inventory shows 121 stockouts and $12.4M excess, MAPE is **9.1%**, and order "
        "automation is at **78.4%**. The highest-value action is resolving the EMEA "
        "capacity shortfall ($4.2M impact) and the FG-55102 stockout ($421K at risk). "
        "Which area would you like to explore?"
    ),
    "follow_ups": [
        "What is the financial impact of the EMEA capacity gap?",
        "Which supplier is causing the most order exceptions?",
        "What will inventory turns be next quarter at current trajectory?",
    ],
}


def _pick_fallback(question: str) -> dict:
    q = question.lower()
    best = _DEFAULT_RESPONSE
    best_score = 0
    for item in _FALLBACK_RESPONSES:
        score = sum(1 for kw in item["keywords"] if kw in q)
        if score > best_score:
            best_score = score
            best = item
    return best


@app.route("/api/ai-chat", methods=["POST"])
@login_required
def ai_chat():
    data     = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question required"}), 400

    # Try live Genie space if configured
    if GENIE_SPACE_ID:
        try:
            host, hdrs = _genie_creds()
            print(f"[Genie] starting conversation space={GENIE_SPACE_ID}", flush=True)
            # 1. Start conversation
            r1 = requests.post(
                f"{host}/api/2.0/genie/spaces/{GENIE_SPACE_ID}/start-conversation",
                headers=hdrs,
                json={"content": question},
                timeout=30,
            )
            print(f"[Genie] start status={r1.status_code}", flush=True)
            if r1.status_code != 200:
                print(f"[Genie] start error body={r1.text[:300]}", flush=True)
            if r1.status_code == 200:
                conv_id = r1.json().get("conversation_id", "")
                msg_id  = r1.json().get("message_id", "")
                print(f"[Genie] conv_id={conv_id} msg_id={msg_id}", flush=True)
                if conv_id and msg_id:
                    # 2. Poll until COMPLETED (Genie is async — max ~45s)
                    msg_url = f"{host}/api/2.0/genie/spaces/{GENIE_SPACE_ID}/conversations/{conv_id}/messages/{msg_id}"
                    content = ""
                    for attempt in range(15):
                        time.sleep(3)
                        r2 = requests.get(msg_url, headers=hdrs, timeout=15)
                        if r2.status_code != 200:
                            print(f"[Genie] poll error attempt={attempt} status={r2.status_code} body={r2.text[:200]}", flush=True)
                            break
                        payload = r2.json()
                        status  = payload.get("status", "")
                        print(f"[Genie] poll attempt={attempt} status={status}", flush=True)
                        if status in ("COMPLETED", "FAILED", "CANCELLED"):
                            for att in payload.get("attachments", []):
                                if att.get("text"):
                                    content = att["text"].get("content", "")
                            print(f"[Genie] final status={status} content_len={len(content)}", flush=True)
                            break
                    if content:
                        return jsonify({"answer": content, "sources": ["genie"], "follow_ups": []})
        except Exception as _ge:
            print(f"[Genie] exception: {_ge}", flush=True)

    fb = _pick_fallback(question)
    return jsonify({
        "answer":     fb["answer"],
        "sources":    ["supply_chain_delta_lake"],
        "follow_ups": fb.get("follow_ups", []),
        "simulated":  True,
    })


# ── /api/actions ────────────────────────────────────────────────────────────
# Seeded from gold_agentic_actions — same data, served as JSON for the UI.
# Keyed by entity/keyword so the frontend can match them to Genie answers.

_ACTIONS = [
    {
        "id": "ACT-001", "type": "emergency_reorder", "entity_type": "sku",
        "entity_id": "FG-55102", "entity_name": "Hydraulic Pump Unit",
        "label": "Emergency Reorder",
        "description": "Trigger emergency reorder for FG-55102 — 4 DOS remaining in Chicago DC.",
        "rationale": "Systematic -28% under-forecast bias has depleted safety stock. 3 Apex Industrial orders on hold.",
        "impact_usd": 421000, "priority": "Critical",
        "owner": "Supply Chain Ops", "status": "pending",
        "keywords": ["fg-55102", "hydraulic pump", "stockout", "chicago", "reorder", "stockouts"],
    },
    {
        "id": "ACT-002", "type": "lateral_transfer", "entity_type": "sku",
        "entity_id": "FG-78421", "entity_name": "Premium Sprocket Assembly",
        "label": "Lateral Transfer",
        "description": "Transfer 200 units FG-78421 from Chicago DC → Rotterdam DC (91% utilization).",
        "rationale": "Chicago has 187 DOS excess. Rotterdam at capacity risk. Recovers $284K stranded inventory.",
        "impact_usd": 284000, "priority": "High",
        "owner": "Logistics", "status": "pending",
        "keywords": ["fg-78421", "sprocket", "rotterdam", "excess", "chicago", "transfer", "warehouse"],
    },
    {
        "id": "ACT-003", "type": "update_contract", "entity_type": "supplier",
        "entity_id": "PSUP-PACIFIC", "entity_name": "Pacific Components",
        "label": "Load Q2 Rate Card",
        "description": "Load renewed Q2 contract rate card into ERP for Pacific Components to auto-resolve 18 held POs ($143K).",
        "rationale": "ERP still applying expired Q1 price $41.20 vs agreed Q2 rate $38.50.",
        "impact_usd": 143000, "priority": "High",
        "owner": "Procurement", "status": "pending",
        "keywords": ["pacific components", "price discrepancy", "rate card", "contract", "po", "exceptions"],
    },
    {
        "id": "ACT-004", "type": "expedite_shipment", "entity_type": "po",
        "entity_id": "PO-91207", "entity_name": "EuroTech Supplies — Pump Assembly F",
        "label": "Expedite to Air Freight",
        "description": "Switch PO-91207 from sea to air freight — Rotterdam port backlog causing 6-day delay.",
        "rationale": "Air premium ~$2.1K vs $14K stockout risk. Vessel delayed 6 days at Rotterdam.",
        "impact_usd": 14000, "priority": "High",
        "owner": "Logistics", "status": "pending",
        "keywords": ["po-91207", "eurotech", "rotterdam", "delivery", "delay", "shipment", "expedite"],
    },
    {
        "id": "ACT-005", "type": "post_goods_receipt", "entity_type": "po",
        "entity_id": "PO-84029", "entity_name": "Allied Materials — Actuator M",
        "label": "Post Goods Receipt",
        "description": "Post goods receipt for PO-84029 — goods confirmed in WH-01, ERP receipt pending.",
        "rationale": "Unblocks invoice INV-AP-8841 ($38K) for 3-way match. Goods have been in warehouse 9 days.",
        "impact_usd": 38000, "priority": "Medium",
        "owner": "Warehouse Ops", "status": "pending",
        "keywords": ["po-84029", "allied", "invoice", "unmatched", "goods receipt", "actuator"],
    },
    {
        "id": "ACT-006", "type": "adjust_forecast", "entity_type": "sku",
        "entity_id": "FG-55102", "entity_name": "Hydraulic Pump Unit",
        "label": "Apply Forecast Override +28%",
        "description": "Apply +28% upward override to FG-55102 consensus forecast to correct persistent under-bias.",
        "rationale": "34.2% MAPE, -28% systematic bias over 12 months. Corrects safety stock calculations.",
        "impact_usd": 0, "priority": "Medium",
        "owner": "Demand Planning", "status": "pending",
        "keywords": ["fg-55102", "hydraulic pump", "forecast", "mape", "bias", "demand", "error"],
    },
    {
        "id": "ACT-007", "type": "dual_source", "entity_type": "sku",
        "entity_id": "CP-33901", "entity_name": "Control Module Type C",
        "label": "Initiate Dual-Source RFQ",
        "description": "Issue RFQ to 2 alternative suppliers for CP-33901 and DA-410 to reduce single-source risk.",
        "rationale": "Pacific Components short-shipped 4 POs (8–22%). $218K at risk from single-source dependency.",
        "impact_usd": 218000, "priority": "Medium",
        "owner": "Procurement", "status": "pending",
        "keywords": ["cp-33901", "control module", "pacific", "quantity variance", "dual source", "rfq"],
    },
    {
        "id": "ACT-008", "type": "safety_stock_review", "entity_type": "sku",
        "entity_id": "FG-91033", "entity_name": "Drive Belt Assembly XL",
        "label": "Review Safety Stock Policy",
        "description": "Increase safety stock policy for FG-91033 — currently 3 DOS in Singapore DC.",
        "rationale": "Below 7-day at-risk threshold. 19.4% MAPE with -16.7% bias. $67K revenue exposure.",
        "impact_usd": 67000, "priority": "Medium",
        "owner": "Supply Planning", "status": "pending",
        "keywords": ["fg-91033", "drive belt", "singapore", "stockout", "safety stock", "at risk"],
    },
    {
        "id": "ACT-009", "type": "capacity_escalation", "entity_type": "bu",
        "entity_id": "EMEA", "entity_name": "EMEA Business Unit",
        "label": "Escalate EMEA to S&OP",
        "description": "Escalate EMEA Q3 capacity shortfall ($4.2M) to S&OP Executive Review before May 12.",
        "rationale": "88.7% attainment vs 92% target. Must resolve before Consensus Meeting to protect exec sign-off.",
        "impact_usd": 4200000, "priority": "High",
        "owner": "S&OP", "status": "pending",
        "keywords": ["emea", "capacity", "attainment", "s&op", "ibp", "plan", "shortfall"],
    },
    {
        "id": "ACT-010", "type": "fx_rate_refresh", "entity_type": "supplier",
        "entity_id": "PSUP-PRECISION", "entity_name": "Precision Parts GmbH",
        "label": "Run FX Rate Refresh",
        "description": "Run FX rate refresh job for EUR-denominated POs from Precision Parts GmbH (3 POs, $23.5K).",
        "rationale": "EUR/USD mismatch: invoices at 1.072 vs PO rate 1.089. Auto-resolves on next daily feed run.",
        "impact_usd": 23500, "priority": "Low",
        "owner": "Finance", "status": "pending",
        "keywords": ["precision parts", "fx", "eur", "currency", "invoice", "delivery mismatch"],
    },
]

# In-memory status store (resets on restart; replace with DB write for persistence)
_action_status: dict[str, str] = {}


@app.route("/api/actions")
@login_required
def get_actions():
    actions = []
    for a in _ACTIONS:
        row = {k: v for k, v in a.items() if k != "keywords"}
        row["status"] = _action_status.get(a["id"], a["status"])
        actions.append(row)
    return jsonify(actions)


@app.route("/api/actions/suggest", methods=["POST"])
@login_required
def suggest_actions():
    """Return top-3 relevant actions based on keyword match against question + answer."""
    data   = request.get_json(silent=True) or {}
    text   = (data.get("question", "") + " " + data.get("answer", "")).lower()
    scored = []
    for a in _ACTIONS:
        if _action_status.get(a["id"]) in ("approved", "dismissed"):
            continue
        score = sum(1 for kw in a["keywords"] if kw in text)
        if score:
            scored.append((score, a))
    scored.sort(key=lambda x: (-x[0], -x[1]["impact_usd"]))
    result = []
    for _, a in scored[:3]:
        row = {k: v for k, v in a.items() if k != "keywords"}
        row["status"] = _action_status.get(a["id"], a["status"])
        result.append(row)
    return jsonify(result)


@app.route("/api/actions/execute", methods=["POST"])
@login_required
def execute_action():
    data      = request.get_json(silent=True) or {}
    action_id = data.get("action_id", "")
    outcome   = data.get("outcome", "approved")   # "approved" | "dismissed"
    if not action_id:
        return jsonify({"error": "action_id required"}), 400
    _action_status[action_id] = outcome
    user = (request.headers.get("X-Forwarded-User") or session.get("email", "user"))
    print(f"[Action] {action_id} -> {outcome} by {user}", flush=True)
    return jsonify({"action_id": action_id, "outcome": outcome, "executed_by": user})


# ── Genie Debug ─────────────────────────────────────────────────────────────────
@app.route("/api/debug/genie")
@login_required
def debug_genie():
    report = {
        "genie_space_id":    GENIE_SPACE_ID,
        "host_set":          bool(os.getenv("DATABRICKS_HOST")),
        "token_set":         bool(os.getenv("DATABRICKS_TOKEN")),
        "client_id_set":     bool(os.getenv("DATABRICKS_CLIENT_ID")),
        "client_secret_set": bool(os.getenv("DATABRICKS_CLIENT_SECRET")),
        "start_status": None,
        "start_body":   None,
        "poll_status":  None,
        "poll_body":    None,
        "answer":       None,
        "error":        None,
    }
    try:
        host, hdrs = _genie_creds()
        report["host"] = host
        r1 = requests.post(
            f"{host}/api/2.0/genie/spaces/{GENIE_SPACE_ID}/start-conversation",
            headers=hdrs, json={"content": "What is the total inventory value?"}, timeout=30,
        )
        report["start_status"] = r1.status_code
        report["start_body"]   = r1.json() if r1.status_code == 200 else r1.text[:500]
        if r1.status_code == 200:
            conv_id = r1.json().get("conversation_id", "")
            msg_id  = r1.json().get("message_id", "")
            if conv_id and msg_id:
                msg_url = f"{host}/api/2.0/genie/spaces/{GENIE_SPACE_ID}/conversations/{conv_id}/messages/{msg_id}"
                for _ in range(10):
                    time.sleep(3)
                    r2 = requests.get(msg_url, headers=hdrs, timeout=15)
                    report["poll_status"] = r2.status_code
                    if r2.status_code != 200:
                        report["poll_body"] = r2.text[:500]
                        break
                    payload = r2.json()
                    status  = payload.get("status", "")
                    if status in ("COMPLETED", "FAILED", "CANCELLED"):
                        report["poll_body"] = payload
                        for att in payload.get("attachments", []):
                            if att.get("text"):
                                report["answer"] = att["text"].get("content", "")
                        break
    except Exception as e:
        report["error"] = str(e)
    return jsonify(report)


# ── Lakebase Debug ──────────────────────────────────────────────────────────────
@app.route("/api/debug/lakebase")
@login_required
def debug_lakebase():
    report = {
        "lakebase_ok":   _LAKEBASE_OK,
        "psycopg2_ok":   _PSYCOPG2_OK,
        "host":          LAKEBASE_HOST,
        "db":            LAKEBASE_DB,
        "user":          LAKEBASE_USER,
        "endpoint":      LAKEBASE_ENDPOINT,
        "databricks_host_set": bool(os.getenv("DATABRICKS_HOST")),
        "databricks_token_set": bool(os.getenv("DATABRICKS_TOKEN")),
        "token_ok":      False,
        "connect_ok":    False,
        "row_count":     None,
        "error":         None,
    }
    host          = os.getenv("DATABRICKS_HOST", "").rstrip("/")
    if host and not host.startswith("http"):
        host = f"https://{host}"
    client_id     = os.getenv("DATABRICKS_CLIENT_ID", "")
    client_secret = os.getenv("DATABRICKS_CLIENT_SECRET", "")
    report["client_id_set"]     = bool(client_id)
    report["client_secret_set"] = bool(client_secret)

    # Step 1: get M2M bearer token
    bearer = None
    try:
        r = requests.post(
            f"{host}/oidc/v1/token",
            data={"grant_type": "client_credentials", "scope": "all-apis"},
            auth=(client_id, client_secret),
            timeout=10,
        )
        report["oauth_status"] = r.status_code
        report["oauth_body"]   = r.text[:500]
        r.raise_for_status()
        bearer = r.json().get("access_token")
        report["bearer_ok"] = bool(bearer)
    except Exception as e:
        report["oauth_error"] = str(e)

    # Step 2: generate Lakebase credential
    tok = None
    if bearer:
        try:
            r2 = requests.post(
                f"{host}/api/2.0/postgres/credentials",
                headers={"Authorization": f"Bearer {bearer}"},
                json={"endpoint": LAKEBASE_ENDPOINT},
                timeout=10,
            )
            report["lakebase_cred_status"] = r2.status_code
            report["lakebase_cred_body"]   = r2.text[:500]
            r2.raise_for_status()
            tok = r2.json().get("token")
            report["token_ok"] = bool(tok)
        except Exception as e:
            report["lakebase_cred_error"] = str(e)

    # Step 3: connect
    if tok:
        try:
            with _db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM page_time_log")
                    report["row_count"] = cur.fetchone()[0]
            report["connect_ok"] = True
        except Exception as e:
            report["error"] = str(e)

    return jsonify(report)

# ── Page Time Logging ───────────────────────────────────────────────────────────
@app.route("/api/log-page-time", methods=["POST"])
@login_required
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
                    (user, page, seconds, "Supply Chain Intelligence"),
                )
            conn.commit()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
