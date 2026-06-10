# Azure Deployment Guide — Solution Studio

This document covers the full Azure deployment for Solution Studio at
**`mfg.databricks-demo.com`**.

---

## Architecture

```
Browser
  │  HTTPS
  ▼
Azure Front Door (CDN / TLS termination)
  profile:   databricks-manufacturing-fd   (Standard_AzureFrontDoor)
  endpoint:  databricks-manufacturing-ghcmeffsbve2brbk.a02.azurefd.net
  domain:    mfg.databricks-demo.com
  │  HTTPS, Host: mfg.databricks-demo.com
  ▼
Azure App Service
  name:      databricks-manufacturing-apps
  rg:        databricks-manufacturing-apps-rg
  url:       databricks-manufacturing-apps.azurewebsites.net  (direct access blocked)
  runtime:   Python 3.11, Standard S1
```

Direct access to `azurewebsites.net` is **blocked** — only traffic routed through
Front Door is allowed (enforced via App Service access restrictions).

---

## Prerequisites

```bash
# Authenticate
az login
az account set --subscription "<your-subscription-id>"

# Confirm correct subscription
az account show --query "{name:name,id:id}"
```

---

## One-Time Infrastructure Setup

> Skip this section if the infrastructure already exists. Jump to
> [Day-to-Day Deploy](#day-to-day-deploy).

### 1. Resource group

```bash
az group create \
  --name databricks-manufacturing-apps-rg \
  --location eastus
```

### 2. App Service Plan + Web App

```bash
# App Service Plan (Standard S1 — needed for custom domains + access restrictions)
az appservice plan create \
  --resource-group databricks-manufacturing-apps-rg \
  --name databricks-manufacturing-apps-plan \
  --sku S1 \
  --is-linux

# Web App — Python 3.11
az webapp create \
  --resource-group databricks-manufacturing-apps-rg \
  --plan databricks-manufacturing-apps-plan \
  --name databricks-manufacturing-apps \
  --runtime "PYTHON:3.11"
```

### 3. Startup command

The `--pythonpath` flag ensures `api.py` is always importable regardless of
where Oryx extracts the zip.

```bash
az webapp config set \
  --resource-group databricks-manufacturing-apps-rg \
  --name databricks-manufacturing-apps \
  --startup-file "gunicorn --bind=0.0.0.0:8000 --workers 2 --threads 4 --timeout 180 --pythonpath /home/site/wwwroot api:app"
```

### 4. App settings (environment variables)

Replace placeholder values with real ones before running. Secrets (API keys,
credentials) should be stored in a password manager and injected here — never
committed to source control.

```bash
az webapp config appsettings set \
  --resource-group databricks-manufacturing-apps-rg \
  --name databricks-manufacturing-apps \
  --settings \
    ENABLE_ORYX_BUILD=true \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true \
    SECRET_KEY="<generate: python3 -c 'import secrets; print(secrets.token_hex(32))'>" \
    ANTHROPIC_API_KEY="<sk-ant-api03-...>" \
    GOOGLE_CREDENTIALS_B64="<base64 of GCP service-account JSON>" \
    FIN_GOOGLE_API_KEY="<AIzaSy... or AQ.Ab8...>" \
    DATABRICKS_HOST="https://fevm-solution-studio.cloud.databricks.com" \
    DATABRICKS_TOKEN="<dapi...>" \
    GENIE_HOST="https://db-dais-2026.cloud.databricks.com" \
    GENIE_CLIENT_ID="<oauth-client-id>" \
    GENIE_CLIENT_SECRET="<oauth-client-secret>" \
    GENIE_TOKEN="<dapi...>" \
    SC_GENIE_SPACE_ID="01f160fc046619db8379001c11fe5511" \
    MFG_GENIE_SPACE_ID="01f163fffd5e15108101b47325134dd5" \
    FIN_GENIE_SPACE_ID="01f163fffd161220a7f76e9968093b68" \
    SALES_GENIE_SPACE_ID="01f163fffd8a184dbe8a8c2de132913b" \
    SC_LLM_ENDPOINT="databricks-meta-llama-3-3-70b-instruct" \
    SC_SQL_WAREHOUSE_HTTP_PATH="/sql/1.0/warehouses/17e5cb93c5f1758e" \
    MFG_SQL_WAREHOUSE_HTTP_PATH="/sql/1.0/warehouses/17e5cb93c5f1758e" \
    MFG_VISION_ENDPOINT="vision" \
    MFG_PDM_ENDPOINT="predictive-maintenance" \
    MFG_MANUALS_ENDPOINT="mfg-manuals-rag" \
    MFG_UC_CATALOG="solution_studio_catalog" \
    MFG_UC_SCHEMA="mfg_vision" \
    MFG_UC_VOLUME="inspection_images" \
    FIN_WAREHOUSE_ID="17e5cb93c5f1758e" \
    FIN_CATALOG="solution_studio_catalog" \
    FIN_GOLD_SCHEMA="finance_gold" \
    LOG_SHEET_ID="1IcUqjBdtb__MHmgozi2RgsVzmizN_SUZp0Fdt8ympDs" \
    COMPANY_NAME=""
```

### 5. Azure Front Door

```bash
# Create profile
az afd profile create \
  --resource-group databricks-manufacturing-apps-rg \
  --profile-name databricks-manufacturing-fd \
  --sku Standard_AzureFrontDoor

# Create endpoint
az afd endpoint create \
  --resource-group databricks-manufacturing-apps-rg \
  --profile-name databricks-manufacturing-fd \
  --endpoint-name databricks-manufacturing \
  --enabled-state Enabled

# Create origin group (health probe against /health)
az afd origin-group create \
  --resource-group databricks-manufacturing-apps-rg \
  --profile-name databricks-manufacturing-fd \
  --origin-group-name appservice-origin-group \
  --probe-request-type GET \
  --probe-protocol Https \
  --probe-interval-in-seconds 30 \
  --probe-path "/health" \
  --sample-size 4 \
  --successful-samples-required 3

# Add App Service as origin
# IMPORTANT: origin-host-header must be the PUBLIC custom domain (not azurewebsites.net).
# If it points to azurewebsites.net, Flask uses that hostname when building redirect
# URLs, causing trailing-slash redirects to go to the blocked backend hostname.
az afd origin create \
  --resource-group databricks-manufacturing-apps-rg \
  --profile-name databricks-manufacturing-fd \
  --origin-group-name appservice-origin-group \
  --origin-name appservice-primary \
  --host-name databricks-manufacturing-apps.azurewebsites.net \
  --origin-host-header mfg.databricks-demo.com \
  --http-port 80 \
  --https-port 443 \
  --priority 1 \
  --weight 1000 \
  --enabled-state Enabled

# Create route: forward all traffic, HTTPS only, HTTPS redirect enabled
az afd route create \
  --resource-group databricks-manufacturing-apps-rg \
  --profile-name databricks-manufacturing-fd \
  --endpoint-name databricks-manufacturing \
  --route-name main \
  --origin-group appservice-origin-group \
  --supported-protocols Https \
  --patterns-to-match "/*" \
  --forwarding-protocol HttpsOnly \
  --https-redirect Enabled \
  --link-to-default-domain Enabled
```

### 6. Custom domain

Point your DNS CNAME for `mfg.databricks-demo.com` at the Front Door endpoint
hostname (`databricks-manufacturing-ghcmeffsbve2brbk.a02.azurefd.net`), then
associate the domain:

```bash
az afd custom-domain create \
  --resource-group databricks-manufacturing-apps-rg \
  --profile-name databricks-manufacturing-fd \
  --custom-domain-name mfg-databricks-demo-com \
  --host-name mfg.databricks-demo.com \
  --minimum-tls-version TLS12 \
  --certificate-type ManagedCertificate

# Link custom domain to the route
az afd route update \
  --resource-group databricks-manufacturing-apps-rg \
  --profile-name databricks-manufacturing-fd \
  --endpoint-name databricks-manufacturing \
  --route-name main \
  --custom-domains mfg-databricks-demo-com
```

### 7. Lock down App Service — allow only Front Door

Retrieve the Front Door ID, then create an access restriction that blocks all
direct requests to `azurewebsites.net`:

```bash
AFD_ID=$(az afd profile show \
  --resource-group databricks-manufacturing-apps-rg \
  --profile-name databricks-manufacturing-fd \
  --query id --output tsv)

az webapp config access-restriction add \
  --resource-group databricks-manufacturing-apps-rg \
  --name databricks-manufacturing-apps \
  --rule-name AllowOurFrontDoor \
  --priority 100 \
  --action Allow \
  --service-tag AzureFrontDoor.Backend \
  --headers "X-Azure-FDID=$AFD_ID"
```

The default-deny rule is added automatically. Confirm with:

```bash
az webapp config access-restriction show \
  --resource-group databricks-manufacturing-apps-rg \
  --name databricks-manufacturing-apps \
  --query "ipSecurityRestrictions[].{name:name,action:action,priority:priority}"
```

---

## Day-to-Day Deploy

> This is the only command needed for routine code pushes.

**Critical**: `cd solution_studio_app` FIRST. Zipping from the repo root puts
`api.py` at `solution_studio_app/api.py` inside the archive; Oryx then extracts
it into a subdirectory and gunicorn can't find `api:app`.

```bash
cd "/Users/noel.hoxie/Claud Code/solution_studio_app" && \
  zip -r /tmp/solution_studio_app.zip . \
    --exclude "*.pyc" \
    --exclude "__pycache__/*" \
    --exclude ".DS_Store" \
    --exclude ".venv/*" \
    --exclude "tests/__pycache__/*" \
    -q && \
  az webapp deploy \
    --resource-group databricks-manufacturing-apps-rg \
    --name databricks-manufacturing-apps \
    --src-path /tmp/solution_studio_app.zip \
    --type zip \
    --async true
```

**Timings** (approximate):
- `az webapp deploy` returns immediately (async)
- Oryx build (pip install): ~400 s
- Container start after build: ~55 s
- Total time to live: ~8 min

Check deployment status:

```bash
az webapp deployment list-publishing-credentials \
  --resource-group databricks-manufacturing-apps-rg \
  --name databricks-manufacturing-apps \
  --query "publishingUserName" --output tsv

# Or check the last deployment result:
az webapp log deployment list \
  --resource-group databricks-manufacturing-apps-rg \
  --name databricks-manufacturing-apps \
  --query "[0].{status:deploymentStatus,message:message}" --output json
```

Tail live logs while the container starts:

```bash
az webapp log tail \
  --resource-group databricks-manufacturing-apps-rg \
  --name databricks-manufacturing-apps
```

---

## Verify the Deployment

```bash
# Health probe (bypasses Front Door for a quick backend check)
curl -sv "https://mfg.databricks-demo.com/health"

# Confirm trailing-slash redirects point to the custom domain (not azurewebsites.net)
curl -sv "https://mfg.databricks-demo.com/manufacturing" 2>&1 | grep "^< location"
curl -sv "https://mfg.databricks-demo.com/finance"       2>&1 | grep "^< location"
curl -sv "https://mfg.databricks-demo.com/supply-chain"  2>&1 | grep "^< location"
# All three should return: location: https://mfg.databricks-demo.com/<module>/

# Confirm security headers are present
curl -sI "https://mfg.databricks-demo.com/" | grep -E "X-Content-Type|X-Frame|Referrer|Permissions|Content-Security"
```

Expected security headers:

```
X-Content-Type-Options: nosniff
X-Frame-Options: SAMEORIGIN
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
Content-Security-Policy: default-src 'self'; ...
```

---

## Key Design Decisions

### ProxyFix middleware (in `api.py`)

```python
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
```

Azure Front Door sets `X-Forwarded-Host` and `X-Forwarded-Proto` on every
request it forwards. Without ProxyFix, Flask ignores those headers and builds
redirect URLs from the `Host` header it actually sees — which is the App Service
origin hostname. With ProxyFix, Flask reads the forwarded headers and generates
correct `https://mfg.databricks-demo.com/...` redirect URLs.

**Symptom without this fix:** visiting `/manufacturing` redirects to
`http://databricks-manufacturing-apps.azurewebsites.net/manufacturing/` — a
direct backend URL that is blocked by the access restriction, resulting in a 403.

### `origin-host-header` must be the public domain

The Front Door origin is configured with `originHostHeader: mfg.databricks-demo.com`
(not `databricks-manufacturing-apps.azurewebsites.net`). This sets the `Host`
header that App Service receives. Flask/ProxyFix uses `X-Forwarded-Host` from
Front Door for redirect URLs, but the `Host` header must still be a valid
hostname the app accepts. Using the public domain here keeps routing consistent
even if ProxyFix is removed.

To update the origin host header:

```bash
az afd origin update \
  --resource-group databricks-manufacturing-apps-rg \
  --profile-name databricks-manufacturing-fd \
  --origin-group-name appservice-origin-group \
  --origin-name appservice-primary \
  --origin-host-header mfg.databricks-demo.com
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| 403 on `/manufacturing`, `/finance`, `/supply-chain` | Trailing-slash redirect going to `azurewebsites.net` | Check ProxyFix is in `api.py`; check Front Door `originHostHeader` |
| 403 on any URL | Direct `azurewebsites.net` access bypassing Front Door | Add access restriction (step 7 above) |
| `No module named 'api'` on startup | Zip packaged from repo root, not `solution_studio_app/` | `cd solution_studio_app` before zipping |
| Sessions lost on restart | `SECRET_KEY` not set | Set `SECRET_KEY` app setting to a stable hex value |
| Build timeout / 230 s Azure timeout | `_ensure_log_tables()` blocking gunicorn workers | Confirm it runs in a background thread in `api.py` |
| Security headers missing | `_security_headers` after_request hook not in `api.py` | Redeploy from `dais2026-hardening` branch |
| Clearbit logo fetch blocked | CSP missing `connect-src` for Clearbit | Confirm CSP `connect-src 'self' https://autocomplete.clearbit.com` |

---

## Security Checklist (post-deploy)

- [ ] `SECRET_KEY` app setting is set (stable random hex, not empty)
- [ ] Direct `azurewebsites.net` access returns 403
- [ ] All 5 security headers present on every response
- [ ] No secrets committed to source control (`.env`, `app.yaml` uses `valueFrom`, Azure uses app settings)
- [ ] GCP service-account key rotated (old key ID `39763801c7b892aef46c4dbdf990ac327c8201d6` was committed in git history — revoke in GCP Console → `gcp-sandbox-field-eng` project)
- [ ] `HTTPS Only` enabled on App Service
- [ ] Front Door route has HTTPS redirect enabled

Enable HTTPS only if not already set:

```bash
az webapp update \
  --resource-group databricks-manufacturing-apps-rg \
  --name databricks-manufacturing-apps \
  --https-only true
```
