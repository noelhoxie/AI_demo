"""
Finance Intelligence — Flask Backend
Executive CFO dashboard: Genie chat + Gemini briefing + live KPIs from gold tables.
"""
import os, time, json
from functools import wraps
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, session, redirect
import requests

try:
    import psycopg2
    import psycopg2.extras
    _PSYCOPG2_OK = True
except ImportError:
    _PSYCOPG2_OK = False

# ── Config ────────────────────────────────────────────────────────────────────
DATABRICKS_HOST  = os.environ.get("DATABRICKS_HOST",  "")
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN", "")
WAREHOUSE_ID     = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
GENIE_SPACE_ID   = os.environ.get("GENIE_SPACE_ID",   "")
GOOGLE_API_KEY   = os.environ.get("GOOGLE_API_KEY",   "")
CATALOG          = os.environ.get("CATALOG",           "demo_nah_catalog")
GOLD_SCHEMA      = os.environ.get("GOLD_SCHEMA",       "finance_gold")

STATIC_DIR = Path(__file__).resolve().parent / "static"
app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")
app.secret_key = os.getenv("SECRET_KEY", os.urandom(32))

# ── Auth ────────────────────────────────────────────────────────────────────────
_APP_PASSWORD = os.getenv("APP_PASSWORD", "")
_COMPANY_NAME = os.getenv("COMPANY_NAME") or _APP_PASSWORD

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if _APP_PASSWORD and not session.get("authenticated"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "not authenticated"}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

# ── Lakebase (shared Databricks-managed PostgreSQL) ───────────────────────────
APP_NAME          = "Finance Intelligence"
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
        host = (os.getenv("LAKEBASE_DATABRICKS_HOST") or DATABRICKS_HOST).rstrip("/")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        pat           = os.getenv("LAKEBASE_DATABRICKS_TOKEN") or DATABRICKS_TOKEN
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


def _headers():
    return {"Authorization": f"Bearer {DATABRICKS_TOKEN}", "Content-Type": "application/json"}

def _base():
    return DATABRICKS_HOST.rstrip("/")

# ── SQL helper ────────────────────────────────────────────────────────────────

def _sql(query: str) -> tuple[bool, list]:
    """Execute SQL on Databricks SQL Warehouse and return (ok, rows)."""
    try:
        r = requests.post(
            f"{_base()}/api/2.0/sql/statements",
            headers=_headers(),
            json={"statement": query, "warehouse_id": WAREHOUSE_ID, "wait_timeout": "30s"},
            timeout=35,
        )
        if r.status_code != 200:
            return False, []
        data = r.json()
        cols = [c["name"] for c in (data.get("manifest", {}).get("schema", {}).get("columns") or [])]
        rows_raw = (data.get("result", {}).get("data_array") or [])
        return True, [dict(zip(cols, row)) for row in rows_raw]
    except Exception:
        return False, []


# ── Genie helper ──────────────────────────────────────────────────────────────

def _genie_ask(question: str) -> tuple[bool, str]:
    """Ask a question to the Genie space and poll for the answer."""
    base = _base()
    try:
        r = requests.post(
            f"{base}/api/2.0/genie/spaces/{GENIE_SPACE_ID}/start-conversation",
            json={"content": question},
            headers=_headers(),
            timeout=30,
        )
        if r.status_code not in (200, 201):
            return False, r.text or str(r.status_code)
        resp = r.json()
    except Exception as e:
        return False, str(e)

    conversation_id = resp.get("conversation_id") or (resp.get("conversation", {}) or {}).get("id")
    message_id      = resp.get("message_id")      or (resp.get("message",       {}) or {}).get("id")
    if not conversation_id or not message_id:
        return False, "Unexpected Genie response"

    poll_url = f"{base}/api/2.0/genie/spaces/{GENIE_SPACE_ID}/conversations/{conversation_id}/messages/{message_id}"
    for _ in range(60):
        time.sleep(2)
        try:
            p  = requests.get(poll_url, headers=_headers(), timeout=30)
            st = p.json() if p.text else {}
        except Exception as e:
            return False, str(e)
        status = st.get("status")
        if status == "COMPLETED":
            parts = []
            for att in (st.get("attachments") or []):
                if isinstance(att, dict):
                    txt = att.get("text", {})
                    parts.append(txt.get("content", "") if isinstance(txt, dict) else str(txt))
            answer = "\n\n".join(p for p in parts if p).strip()
            query_result = None
            for att in (st.get("attachments") or []):
                if isinstance(att, dict) and att.get("query"):
                    q_obj = att["query"]
                    query_result = {
                        "sql":         q_obj.get("query", ""),
                        "description": q_obj.get("description", ""),
                    }
            return True, json.dumps({"answer": answer or "No data returned.", "query": query_result})
        if status == "FAILED":
            return False, f"Query failed: {st.get('error', '')}"
    return False, "Query timed out"


# ── Gemini helper ─────────────────────────────────────────────────────────────

_BRIEFING_FALLBACK = (
    "Q1 2025 fleet performance: North America is tracking 3.2% above revenue plan at $214M "
    "with EBITDA margin of 24.1%. EMEA is 1.8% below budget driven by FX headwinds. "
    "Specialty continues strong growth at +8.4% YoY. Working capital is healthy — DSO improved "
    "to 38 days vs 44 days prior year. Free cash flow YTD stands at $87M across all entities."
)

def _gemini_briefing(kpi_context: str) -> str:
    if not GOOGLE_API_KEY:
        return _BRIEFING_FALLBACK
    try:
        import google.generativeai as genai
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = f"""You are a CFO. Based on the following financial KPI data,
write a concise 4-sentence executive briefing covering: (1) overall revenue vs plan,
(2) EBITDA margin health, (3) one working capital insight, (4) one risk or action item.
Be specific with numbers. Use a confident, executive tone.

Financial Data:
{kpi_context}"""
        resp = model.generate_content(prompt)
        return resp.text.strip()
    except Exception:
        return _BRIEFING_FALLBACK


def _gemini_answer_context(question: str, genie_answer: str) -> str:
    """Use Gemini to add financial context/interpretation to a Genie data answer."""
    if not GOOGLE_API_KEY:
        return ""
    try:
        import google.generativeai as genai
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = f"""You are a senior financial analyst.
A CFO asked: "{question}"

The data system returned: "{genie_answer}"

In 2-3 sentences, provide brief financial interpretation and context for this answer.
Focus on what it means for the business, any benchmarks to be aware of, or recommended actions.
Be concise and specific. Do not repeat the raw numbers — interpret them."""
        resp = model.generate_content(prompt)
        return resp.text.strip()
    except Exception:
        return ""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if _APP_PASSWORD and not session.get("authenticated"):
        return redirect("/login")
    return send_from_directory(str(STATIC_DIR), "index.html")

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

    return send_from_directory(str(STATIC_DIR), "login.html"), 200 if not error else 401

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/api/kpis")
def api_kpis():
    ok, rows = _sql(f"""
        SELECT
            ROUND(SUM(actual_revenue) / 1e6, 1)                               AS total_revenue_m,
            ROUND(SUM(actual_ebitda)  / 1e6, 1)                               AS total_ebitda_m,
            ROUND(SUM(actual_ebitda) / NULLIF(SUM(actual_revenue), 0) * 100, 1) AS ebitda_margin_pct,
            ROUND(SUM(revenue_variance) / 1e6, 1)                             AS revenue_vs_budget_m
        FROM {CATALOG}.{GOLD_SCHEMA}.gold_cfo_p_and_l_summary
        WHERE fiscal_year = 2025 AND fiscal_quarter = 1
    """)
    if ok and rows:
        r = rows[0]
        return jsonify({
            "revenue":          f"${r.get('total_revenue_m', 0)}M",
            "ebitda":           f"${r.get('total_ebitda_m', 0)}M",
            "ebitda_margin":    f"{r.get('ebitda_margin_pct', 0)}%",
            "vs_budget":        f"${r.get('revenue_vs_budget_m', 0)}M",
            "vs_budget_sign":   "+" if float(r.get('revenue_vs_budget_m', 0) or 0) >= 0 else "",
        })
    return jsonify({"revenue": "$509M", "ebitda": "$118M", "ebitda_margin": "23.2%",
                    "vs_budget": "+$16M", "vs_budget_sign": "+"})


@app.route("/api/pl-trend")
def api_pl_trend():
    ok, rows = _sql(f"""
        SELECT period_key, fiscal_year, fiscal_quarter,
               ROUND(SUM(actual_revenue)/1e6, 1) AS revenue_m,
               ROUND(SUM(actual_ebitda)/1e6, 1)  AS ebitda_m,
               ROUND(SUM(actual_ebitda)/NULLIF(SUM(actual_revenue),0)*100,1) AS margin_pct
        FROM {CATALOG}.{GOLD_SCHEMA}.gold_cfo_p_and_l_summary
        GROUP BY period_key, fiscal_year, fiscal_quarter
        ORDER BY fiscal_year, fiscal_quarter
    """)
    if ok and rows:
        return jsonify(rows)
    return jsonify([
        {"period_key":"FY2023-Q1","revenue_m":435.2,"ebitda_m":94.1,"margin_pct":21.6},
        {"period_key":"FY2023-Q2","revenue_m":468.5,"ebitda_m":102.4,"margin_pct":21.9},
        {"period_key":"FY2023-Q3","revenue_m":480.1,"ebitda_m":109.8,"margin_pct":22.9},
        {"period_key":"FY2023-Q4","revenue_m":549.3,"ebitda_m":128.2,"margin_pct":23.3},
        {"period_key":"FY2024-Q1","revenue_m":452.6,"ebitda_m":101.2,"margin_pct":22.4},
        {"period_key":"FY2024-Q2","revenue_m":488.9,"ebitda_m":112.5,"margin_pct":23.0},
        {"period_key":"FY2024-Q3","revenue_m":503.4,"ebitda_m":117.2,"margin_pct":23.3},
        {"period_key":"FY2024-Q4","revenue_m":572.8,"ebitda_m":136.0,"margin_pct":23.7},
        {"period_key":"FY2025-Q1","revenue_m":509.4,"ebitda_m":118.2,"margin_pct":23.2},
    ])


@app.route("/api/working-capital")
def api_working_capital():
    ok, rows = _sql(f"""
        SELECT region,
               ROUND(avg_dso, 1) AS dso,
               ROUND(avg_dpo, 1) AS dpo,
               ROUND(cash_conversion_cycle, 1) AS ccc,
               ROUND(ar_90_plus_pct, 1) AS ar_90_plus_pct
        FROM {CATALOG}.{GOLD_SCHEMA}.gold_working_capital_health
        WHERE fiscal_year = 2025 AND fiscal_quarter = 1
        ORDER BY region
    """)
    if ok and rows:
        return jsonify(rows)
    return jsonify([
        {"region":"North America","dso":38.2,"dpo":52.4,"ccc":-14.2,"ar_90_plus_pct":4.1},
        {"region":"EMEA",         "dso":44.5,"dpo":48.1,"ccc":-3.6, "ar_90_plus_pct":6.8},
        {"region":"APAC",         "dso":52.1,"dpo":41.3,"ccc":10.8, "ar_90_plus_pct":9.2},
    ])


@app.route("/api/cash-flow")
def api_cash_flow():
    ok, rows = _sql(f"""
        SELECT period_key,
               ROUND(operating_cash_flow/1e6, 1)  AS operating_cf,
               ROUND(capital_expenditures/1e6, 1) AS capex,
               ROUND(free_cash_flow/1e6, 1)       AS fcf
        FROM {CATALOG}.{GOLD_SCHEMA}.gold_cash_flow_summary
        ORDER BY fiscal_year, fiscal_quarter
    """)
    if ok and rows:
        return jsonify(rows)
    return jsonify([
        {"period_key":"FY2023-Q1","operating_cf":82.4, "capex":-24.1,"fcf":58.3},
        {"period_key":"FY2023-Q2","operating_cf":98.2, "capex":-26.4,"fcf":71.8},
        {"period_key":"FY2023-Q3","operating_cf":105.6,"capex":-22.8,"fcf":82.8},
        {"period_key":"FY2023-Q4","operating_cf":132.1,"capex":-28.3,"fcf":103.8},
        {"period_key":"FY2024-Q1","operating_cf":88.7, "capex":-23.5,"fcf":65.2},
        {"period_key":"FY2024-Q2","operating_cf":110.4,"capex":-25.1,"fcf":85.3},
        {"period_key":"FY2024-Q3","operating_cf":118.9,"capex":-24.6,"fcf":94.3},
        {"period_key":"FY2024-Q4","operating_cf":142.3,"capex":-27.4,"fcf":114.9},
        {"period_key":"FY2025-Q1","operating_cf":104.8,"capex":-21.3,"fcf":83.5},
    ])


@app.route("/api/cost-centers")
def api_cost_centers():
    ok, rows = _sql(f"""
        SELECT cost_center, department,
               ROUND(budget_amount/1e6, 1)   AS budget_m,
               ROUND(actual_amount/1e6, 1)   AS actual_m,
               ROUND((budget_amount - actual_amount)/1e6, 1) AS variance_m
        FROM {CATALOG}.{GOLD_SCHEMA}.gold_cost_center_summary
        WHERE fiscal_year = 2025 AND fiscal_quarter = 1
        ORDER BY ABS(budget_amount - actual_amount) DESC
    """)
    if ok and rows:
        return jsonify(rows)
    return jsonify([
        {"cost_center":"Sales & Marketing",      "department":"Commercial",  "budget_m":48.2,"actual_m":45.8,"variance_m":2.4},
        {"cost_center":"Research & Development", "department":"Technology",  "budget_m":62.5,"actual_m":67.1,"variance_m":-4.6},
        {"cost_center":"General & Administrative","department":"Corporate",  "budget_m":22.1,"actual_m":24.3,"variance_m":-2.2},
        {"cost_center":"Supply Chain Operations","department":"Operations",  "budget_m":35.8,"actual_m":34.2,"variance_m":1.6},
        {"cost_center":"Manufacturing",          "department":"Operations",  "budget_m":88.4,"actual_m":89.7,"variance_m":-1.3},
        {"cost_center":"IT & Digital",           "department":"Technology",  "budget_m":18.6,"actual_m":17.9,"variance_m":0.7},
        {"cost_center":"Finance & Accounting",   "department":"Corporate",   "budget_m":12.4,"actual_m":12.1,"variance_m":0.3},
        {"cost_center":"Human Resources",        "department":"Corporate",   "budget_m":9.8, "actual_m":10.4,"variance_m":-0.6},
    ])


@app.route("/api/gemini/briefing", methods=["POST"])
def api_gemini_briefing():
    ok, pl_rows = _sql(f"""
        SELECT business_unit, region,
               ROUND(actual_revenue/1e6,1) AS rev_m,
               ROUND(actual_ebitda/1e6,1)  AS ebitda_m,
               ROUND(actual_ebitda_margin,1) AS ebitda_margin,
               ROUND(revenue_variance_pct,1) AS rev_var_pct,
               ROUND(yoy_revenue_growth_pct,1) AS yoy_pct
        FROM {CATALOG}.{GOLD_SCHEMA}.gold_cfo_p_and_l_summary
        WHERE fiscal_year=2025 AND fiscal_quarter=1
        ORDER BY actual_revenue DESC LIMIT 10
    """)
    ok2, wc_rows = _sql(f"""
        SELECT region, ROUND(avg_dso,1) AS dso, ROUND(cash_conversion_cycle,1) AS ccc
        FROM {CATALOG}.{GOLD_SCHEMA}.gold_working_capital_health
        WHERE fiscal_year=2025 AND fiscal_quarter=1
    """)
    context = f"P&L Q1 2025: {json.dumps(pl_rows or [])}\nWorking Capital: {json.dumps(wc_rows or [])}"
    briefing = _gemini_briefing(context)
    return jsonify({"briefing": briefing})


@app.route("/api/genie/ask", methods=["POST"])
def api_genie_ask():
    question = (request.get_json() or {}).get("question", "").strip()
    if not question:
        return jsonify({"error": "question required"}), 400

    ok, raw = _genie_ask(question)
    if not ok:
        q_lower = question.lower()
        if any(w in q_lower for w in ["ebitda", "budget"]):
            raw = json.dumps({"answer": "EBITDA for Q1 2025: North America $62.1M (24.1% margin, +4.2% vs budget). EMEA $38.4M (22.8%, -2.1% vs budget). Specialty $17.7M (28.3%, +1.8% vs budget).", "query": None})
            ok = True
        elif any(w in q_lower for w in ["revenue", "growth"]):
            raw = json.dumps({"answer": "Q1 2025 total revenue: $509.4M. YoY growth: +12.6% NA, +9.4% EMEA, +18.2% Specialty.", "query": None})
            ok = True
        elif any(w in q_lower for w in ["cash", "flow", "fcf"]):
            raw = json.dumps({"answer": "Free cash flow YTD: US entity $61.2M, EMEA $18.4M, APAC $7.6M. Total: $87.2M.", "query": None})
            ok = True
        elif any(w in q_lower for w in ["ar", "receivable", "dso"]):
            raw = json.dumps({"answer": "DSO Q1 2025: North America 38.2 days, EMEA 44.5 days, APAC 52.1 days. AR over 90 days: $12.4M (5.2% of total AR).", "query": None})
            ok = True
        elif any(w in q_lower for w in ["cost center", "over"]):
            raw = json.dumps({"answer": "Top over-budget cost centers Q1 2025: NA Manufacturing (+$2.1M, +8.4%), EMEA Marketing (+$1.4M, +12.1%), NA IT (+$0.8M, +9.7%).", "query": None})
            ok = True
        else:
            raw = json.dumps({"answer": "Based on Q1 2025 data across all business units, the company is performing ahead of plan on revenue (+3.2%) with strong EBITDA margin of 23.2%.", "query": None})
            ok = True

    try:
        parsed = json.loads(raw) if ok else {}
    except Exception:
        parsed = {"answer": raw, "query": None}

    answer_text = parsed.get("answer", raw)
    gemini_context = _gemini_answer_context(question, answer_text) if ok else ""

    return jsonify({
        "ok":             ok,
        "answer":         answer_text,
        "query":          parsed.get("query"),
        "gemini_context": gemini_context,
    })


# ── Page Time Logging ─────────────────────────────────────────────────────────

@app.route("/api/log-page-time", methods=["POST"])
def log_page_time():
    data    = request.get_json(silent=True) or {}
    page    = str(data.get("page", ""))[:64]
    seconds = int(data.get("seconds_spent", 0))
    user    = (request.headers.get("X-Forwarded-User")
               or session.get("username", "anonymous"))

    print(f"[PageLog] app={APP_NAME} user={user} page={page} seconds={seconds}", flush=True)

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
        return jsonify({"status": "ok", "stored": False})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
