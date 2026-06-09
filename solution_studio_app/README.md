# Solution Studio

A consolidated Databricks App that showcases industry-vertical analytics
experiences — Supply Chain, Manufacturing, Finance, and Sales — behind a single
shared login and portal. It is a **lead-capture demo**: prospects sign in with
their name and company (no SSO), the company is classified into an industry
vertical, and the portal surfaces the relevant apps. Engagement (logins, page
time, questions, contact requests) is logged to Delta and Google Sheets.

> **Auth model:** the name + company form is a lead-capture gate, **not** a
> security boundary. The app talks to Databricks using its own service
> principal ("app authorization"), so there is no per-user SSO/OBO.

---

## Available apps

All sub-apps run in this one Flask deployment and share the session cookie.

| App | Route | Description |
|-----|-------|-------------|
| **Login** (lead capture) | `/login` | Name + company sign-in; classifies the company into a vertical |
| **Portal** | `/portal` | Landing page listing the apps for the detected vertical |
| **Supply Chain Control Tower** | `/supply-chain/` | IBP, inventory, demand forecasting, order automation, Genie chat |
| **Operational Excellence** | `/manufacturing/` | OEE, predictive maintenance, vision-based defect detection, quality |
| **Financial Intelligence** | `/finance/` | P&L, cash flow, variance analysis, AI executive briefings |
| **Sales Optimization** | `/sales/` | Dynamic pricing, CPQ, next-best-offer, account health |
| **Mobile** | `/mobile/` | QR-code demo SPA (auto-authenticates) with Genie-powered chat |
| **Health** | `/health` | Liveness probe |

Verticals (`manufacturing`, `retail`, `logistics`, `lifesciences`, `utilities`,
`financial`, `energy`) are defined in `api.py`; the active set is chosen from the
company name via keyword match and an optional Claude Haiku classifier.

---

## Architecture

- **Backend:** Flask (`api.py`), served by Gunicorn.
- **Auth to Databricks:** `databricks-sdk` `Config()` resolves the app's service
  principal on Databricks Apps (auto-injected `DATABRICKS_CLIENT_ID/SECRET`),
  falling back to a `DATABRICKS_TOKEN` env var off-platform. See
  `_workspace_creds()`.
- **Data/AI:** Databricks SQL Warehouse + Genie Conversation API, Databricks
  Model Serving (vision, predictive maintenance, manuals RAG), Anthropic Claude,
  and Google Gemini for briefings.
- **Logging:** Delta tables (parameterized SQL) and Google Sheets (service
  account).
- **Frontend:** static HTML/CSS/JS under `static/`.

---

## Configuration

Configuration is environment-driven (see `app.yaml`). Non-secret values
(hosts, warehouse, Genie space IDs, catalog/schema) are set inline; **secrets
are injected from a Databricks secret scope via `valueFrom`** and are never
committed.

| Secret env var | Secret key | Purpose |
|----------------|-----------|---------|
| `SECRET_KEY` | `session_secret_key` | Flask session signing (set this so sessions survive restarts) |
| `GOOGLE_CREDENTIALS_B64` | `google_credentials_b64` | Base64 GCP service-account JSON for Sheets logging |
| `ANTHROPIC_API_KEY` | `anthropic_api_key` | Claude briefings + vertical classification |
| `FIN_GOOGLE_API_KEY` | `fin_google_api_key` | Gemini finance briefings |
| `LAKEBASE_DATABRICKS_TOKEN` | `lakebase_databricks_token` | Lakebase Postgres OAuth |

All AI/logging features degrade gracefully (fallbacks) when their secret is
absent, so the core lead-capture flow works without any of them.

---

## Deployment

Deployed as a Databricks App via the Asset Bundle (`databricks.yml`, target
`solution_studio`).

### 1. Create the secret scope (one-time)

The `valueFrom` references will fail to start until these exist:

```bash
databricks secrets create-scope solution_studio
databricks secrets put-secret  solution_studio session_secret_key
databricks secrets put-secret  solution_studio google_credentials_b64   # rotated GCP key
databricks secrets put-secret  solution_studio anthropic_api_key
databricks secrets put-secret  solution_studio fin_google_api_key
databricks secrets put-secret  solution_studio lakebase_databricks_token
```

### 2. Deploy and run

```bash
# from the repo root
databricks bundle deploy -t solution_studio
databricks bundle run    -t solution_studio solution_studio
```

The app's service principal needs `CAN USE` on the SQL warehouse and `CAN RUN`
on the Genie spaces it queries (declared as resources in `app.yaml`).

### Local run (optional)

```bash
cd solution_studio_app
python3 -m venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
export SECRET_KEY=dev-only DATABRICKS_HOST=... DATABRICKS_TOKEN=... SESSION_COOKIE_SECURE=false
PORT=5000 ./start.sh
```

---

## Testing

Tests live in `tests/` (pytest) and run fully offline — no warehouse, tokens, or
network. They cover routes, the lead-capture/auto-auth behavior, the credential
and Delta-logging helpers, and static regression guards (no committed secrets,
no token leaks, no predictable session key).

```bash
cd solution_studio_app
python3 -m venv .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest          # or just: pytest
```

```
tests/
  conftest.py        # offline fixtures: app, client, auth_client
  test_app.py        # route smoke tests + login gate
  test_auth.py       # lead-capture login, auto-auth, removed token backdoor
  test_helpers.py    # _delta_log_write params, _workspace_creds, classifier, cookies
  test_regression.py # guards against re-introducing fixed security issues
```
