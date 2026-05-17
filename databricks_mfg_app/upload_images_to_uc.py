#!/usr/bin/env python3
"""
Upload E-Coat inspection images to Unity Catalog Volume.
Creates schema and volume if they don't exist, then uploads all 10 PNG files.

Volume path: /Volumes/{UC_CATALOG}/{UC_SCHEMA}/{UC_VOLUME}/
Default:     /Volumes/demo_nah_catalog/mfg_vision/inspection_images/

Usage:
  python3 upload_images_to_uc.py
  UC_CATALOG=my_catalog UC_SCHEMA=my_schema python3 upload_images_to_uc.py
"""

import os
import sys
import requests

# ── Config ─────────────────────────────────────────────────────────────────────
HOST     = os.environ.get("DATABRICKS_HOST", "").rstrip("/")
TOKEN    = os.environ.get("DATABRICKS_TOKEN", "")
CATALOG  = os.environ.get("UC_CATALOG",  "demo_nah_catalog")
SCHEMA   = os.environ.get("UC_SCHEMA",   "mfg_vision")
VOLUME   = os.environ.get("UC_VOLUME",   "inspection_images")

if not HOST or not TOKEN:
    print("ERROR: DATABRICKS_HOST and DATABRICKS_TOKEN must be set.")
    sys.exit(1)

HDRS_JSON = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
HDRS_FILE = {"Authorization": f"Bearer {TOKEN}"}
IMG_DIR   = os.path.join(os.path.dirname(__file__), "static", "img", "inspection")

def api(method, path, **kwargs):
    r = requests.request(method, f"{HOST}{path}", headers=HDRS_JSON, timeout=30, **kwargs)
    return r

def ensure_schema():
    print(f"  Ensuring schema {CATALOG}.{SCHEMA} exists…")
    r = api("GET", f"/api/2.1/unity-catalog/schemas/{CATALOG}.{SCHEMA}")
    if r.status_code == 200:
        print("    Schema already exists.")
        return
    r = api("POST", "/api/2.1/unity-catalog/schemas",
            json={"name": SCHEMA, "catalog_name": CATALOG, "comment": "Manufacturing vision AI data"})
    if r.status_code in (200, 201):
        print("    Schema created.")
    else:
        print(f"    Schema create response {r.status_code}: {r.text[:200]}")

def ensure_volume():
    print(f"  Ensuring volume {CATALOG}.{SCHEMA}.{VOLUME} exists…")
    r = api("GET", f"/api/2.1/unity-catalog/volumes/{CATALOG}.{SCHEMA}.{VOLUME}")
    if r.status_code == 200:
        print("    Volume already exists.")
        return
    r = api("POST", "/api/2.1/unity-catalog/volumes",
            json={"name": VOLUME, "catalog_name": CATALOG, "schema_name": SCHEMA,
                  "volume_type": "MANAGED", "comment": "Automotive E-Coat inspection images"})
    if r.status_code in (200, 201):
        print("    Volume created.")
    else:
        print(f"    Volume create response {r.status_code}: {r.text[:200]}")

def upload_image(filename):
    path = os.path.join(IMG_DIR, filename)
    if not os.path.exists(path):
        print(f"    SKIP {filename} — file not found locally")
        return False
    uc_path = f"/api/2.0/fs/files/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/{filename}"
    with open(path, "rb") as f:
        r = requests.put(f"{HOST}{uc_path}", headers=HDRS_FILE,
                         data=f, timeout=30)
    if r.status_code in (200, 201, 204):
        print(f"    OK  {filename}")
        return True
    else:
        print(f"    ERR {filename}  →  HTTP {r.status_code}: {r.text[:120]}")
        return False

# ── Main ───────────────────────────────────────────────────────────────────────
print(f"\nUploading inspection images to UC Volume")
print(f"  Host:   {HOST}")
print(f"  Volume: /Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/\n")

ensure_schema()
ensure_volume()

images = sorted(f for f in os.listdir(IMG_DIR) if f.endswith(".png"))
print(f"\n  Uploading {len(images)} images…")
ok = sum(upload_image(f) for f in images)
print(f"\nDone — {ok}/{len(images)} images uploaded.")
print(f"UC path: /Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/")
