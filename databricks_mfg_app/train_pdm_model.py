#!/usr/bin/env python3
# Databricks notebook source
"""
Predictive Maintenance Model — Automotive Shop Floor
=====================================================
Seeds machine sensor history into Unity Catalog Delta table,
trains a GradientBoosting failure-probability classifier,
registers the model to UC Model Registry, and creates a
Databricks Model Serving endpoint.

Run this as a Databricks notebook (ML Runtime 14+) or locally
with sklearn + mlflow + databricks-sdk installed.

Catalog: demo_nah_catalog
Schema:  mfg_gold
Table:   machine_sensor_history
Model:   demo_nah_catalog.mfg_gold.pdm_failure_classifier
Endpoint: predictive-maintenance
"""

# COMMAND ----------
import os
import math
import time
import random
import hashlib
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import mlflow
import mlflow.sklearn
from mlflow.models.signature import infer_signature
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import classification_report, roc_auc_score, accuracy_score

HOST     = os.environ.get("DATABRICKS_HOST", "https://fevm-demo-nah.cloud.databricks.com").rstrip("/")
TOKEN    = os.environ.get("DATABRICKS_TOKEN", "os.environ.get("DATABRICKS_TOKEN", "")")
CATALOG  = os.environ.get("UC_CATALOG", "demo_nah_catalog")
SCHEMA   = "mfg_gold"
TABLE    = "machine_sensor_history"
MODEL_UC = f"{CATALOG}.{SCHEMA}.pdm_failure_classifier"
EXP_NAME = "/Users/noel.hoxie@databricks.com/pdm-failure-classifier"
ENDPOINT = "predictive-maintenance"

# COMMAND ----------
# ── Machine definitions — mirrors MACHINES_STATIC in api.py ────────────────────

MACHINES = [
    # id, line, std_temp, std_vibration, std_spindle_load, std_oil_pressure,
    # std_cycle_sec, operating_hours, hours_since_pm, risk_profile
    # risk_profile: 0=normal, 1=degrading, 2=near-failure, 3=currently-faulted
    {"id": "BDY-STM-01", "line": "A", "name": "3,000-Ton Stamping Press",
     "std_temp": 48.4, "std_vib": 2.1, "std_spindle": 62.0, "std_oil": 4.8,
     "std_cycle": 6.0,  "op_hours": 14200, "pm_hours": 820,  "risk": 1},
    {"id": "BDY-WLD-01", "line": "A", "name": "Robotic Welding Cell",
     "std_temp": 52.1, "std_vib": 3.4, "std_spindle": 71.0, "std_oil": 4.2,
     "std_cycle": 90.0, "op_hours": 19800, "pm_hours": 2100, "risk": 3},
    {"id": "BDY-SLD-01", "line": "A", "name": "Sealing & Hemming Station",
     "std_temp": 28.3, "std_vib": 1.8, "std_spindle": 44.0, "std_oil": 3.9,
     "std_cycle": 45.0, "op_hours": 11400, "pm_hours": 980,  "risk": 3},
    {"id": "BDY-INS-01", "line": "A", "name": "CMM Body Dimension Check",
     "std_temp": 22.1, "std_vib": 0.4, "std_spindle": 18.0, "std_oil": 2.1,
     "std_cycle": 30.0, "op_hours": 8700,  "pm_hours": 210,  "risk": 0},
    {"id": "PNT-PRP-01", "line": "B", "name": "Phosphate Pre-Treatment",
     "std_temp": 54.8, "std_vib": 1.2, "std_spindle": 38.0, "std_oil": 3.1,
     "std_cycle": 120.0,"op_hours": 12600, "pm_hours": 440,  "risk": 1},
    {"id": "PNT-ECT-01", "line": "B", "name": "E-Coat Tank (CED)",
     "std_temp": 30.2, "std_vib": 0.8, "std_spindle": 22.0, "std_oil": 2.8,
     "std_cycle": 180.0,"op_hours": 16400, "pm_hours": 1840, "risk": 3},
    {"id": "PNT-BSC-01", "line": "B", "name": "Robotic Base Coat Booth",
     "std_temp": 25.4, "std_vib": 1.1, "std_spindle": 34.0, "std_oil": 3.4,
     "std_cycle": 60.0, "op_hours": 9200,  "pm_hours": 320,  "risk": 0},
    {"id": "PNT-CLR-01", "line": "B", "name": "Clear Coat & Bake Oven",
     "std_temp": 141.0,"std_vib": 0.6, "std_spindle": 29.0, "std_oil": 2.6,
     "std_cycle": 1800.0,"op_hours": 10800,"pm_hours": 280,  "risk": 0},
    {"id": "PNT-INS-01", "line": "B", "name": "Paint Quality Inspection",
     "std_temp": 23.5, "std_vib": 0.3, "std_spindle": 14.0, "std_oil": 1.8,
     "std_cycle": 20.0, "op_hours": 7400,  "pm_hours": 60,   "risk": 0},
    {"id": "PTN-MCH-01", "line": "C", "name": "CNC Block Machining Center",
     "std_temp": 42.3, "std_vib": 2.8, "std_spindle": 68.0, "std_oil": 4.6,
     "std_cycle": 120.0,"op_hours": 22100, "pm_hours": 1600, "risk": 2},
    {"id": "PTN-HAD-01", "line": "C", "name": "Cylinder Head Assembly",
     "std_temp": 31.7, "std_vib": 1.6, "std_spindle": 52.0, "std_oil": 4.1,
     "std_cycle": 96.0, "op_hours": 18300, "pm_hours": 920,  "risk": 1},
    {"id": "PTN-BLD-01", "line": "C", "name": "Engine Build Station",
     "std_temp": 36.8, "std_vib": 2.2, "std_spindle": 58.0, "std_oil": 3.8,
     "std_cycle": 240.0,"op_hours": 20500, "pm_hours": 2400, "risk": 3},
    {"id": "FAL-ASM-01", "line": "S", "name": "Final Assembly Line",
     "std_temp": 26.4, "std_vib": 1.9, "std_spindle": 48.0, "std_oil": 4.0,
     "std_cycle": 60.0, "op_hours": 24800, "pm_hours": 3200, "risk": 3},
]

FEATURE_COLS = [
    "temp_c", "vibration_rms", "spindle_load_pct", "oil_pressure_bar",
    "cycle_time_deviation_pct", "operating_hours", "hours_since_last_pm",
    "fault_count_7d", "alarm_count_24h",
]

# COMMAND ----------
# ── Generate synthetic sensor history ──────────────────────────────────────────

rng = np.random.RandomState(42)

def _noise(scale, n):
    return rng.normal(0, scale, n)

def _gen_machine_history(m, n_points=500):
    """Generate n_points sensor readings per machine.
    risk=0 → mostly normal, few failures
    risk=1 → mild degradation, ~15% failure rate
    risk=2 → heavy degradation, ~45% failure rate
    risk=3 → near/at failure, ~75% failure rate
    """
    risk = m["risk"]
    rows = []

    # Degradation ramp (0→1 over last 30% of observations)
    degrade = np.zeros(n_points)
    if risk >= 1:
        ramp_start = int(n_points * 0.70)
        degrade[ramp_start:] = np.linspace(0, risk / 3.0, n_points - ramp_start)

    failure_prob_base = {0: 0.04, 1: 0.15, 2: 0.45, 3: 0.75}[risk]

    for i in range(n_points):
        d = degrade[i]
        temp = m["std_temp"] + d * 12.0 + _noise(1.2, 1)[0]
        vib  = m["std_vib"]  + d * 2.5  + _noise(0.15, 1)[0]
        spin = m["std_spindle"] + d * 18.0 + _noise(2.0, 1)[0]
        oil  = max(0.5, m["std_oil"] - d * 1.8 + _noise(0.1, 1)[0])
        ct_dev = d * 22.0 + _noise(1.5, 1)[0]  # % deviation from std
        op_hrs = m["op_hours"] + i * 0.5        # accumulate hours
        pm_hrs = min(m["pm_hours"] + i * 0.5, 5000)
        faults = int(max(0, risk * d * 4 + _noise(0.4, 1)[0]))
        alarms = int(max(0, risk * d * 6 + _noise(0.6, 1)[0]))

        # Label: failure within next 24h
        p_fail = failure_prob_base + d * (1 - failure_prob_base) * 0.85
        label  = int(rng.random() < p_fail)

        rows.append({
            "machine_id":             m["id"],
            "line":                   m["line"],
            "machine_name":           m["name"],
            "temp_c":                 round(float(temp), 2),
            "vibration_rms":          round(max(0.01, float(vib)), 3),
            "spindle_load_pct":       round(min(100.0, max(0.0, float(spin))), 1),
            "oil_pressure_bar":       round(float(oil), 2),
            "cycle_time_deviation_pct": round(float(ct_dev), 2),
            "operating_hours":        round(float(op_hrs), 1),
            "hours_since_last_pm":    round(float(pm_hrs), 1),
            "fault_count_7d":         faults,
            "alarm_count_24h":        alarms,
            "failure_within_24h":     label,
        })
    return rows


print("Generating sensor history…")
all_rows = []
for m in MACHINES:
    rows = _gen_machine_history(m, n_points=500)
    fails = sum(r["failure_within_24h"] for r in rows)
    print(f"  {m['id']:16s}  risk={m['risk']}  failures={fails}/500")
    all_rows.extend(rows)

df = pd.DataFrame(all_rows)
print(f"\nTotal rows: {len(df)}  failures: {df['failure_within_24h'].sum()}")

# COMMAND ----------
# ── Write to UC Delta table ─────────────────────────────────────────────────────

try:
    spark  # noqa — only available in Databricks
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
    sdf = spark.createDataFrame(df)
    sdf.write.format("delta").mode("overwrite").option("overwriteSchema", "true") \
       .saveAsTable(f"{CATALOG}.{SCHEMA}.{TABLE}")
    print(f"Written {len(df)} rows → {CATALOG}.{SCHEMA}.{TABLE}")
except NameError:
    print("No Spark session — skipping Delta write (local mode)")

# COMMAND ----------
# ── Train GradientBoosting classifier ──────────────────────────────────────────

X = df[FEATURE_COLS].values.astype(np.float32)
y = df["failure_within_24h"].values

pipe = Pipeline([
    ("scaler", StandardScaler()),
    ("gbm", GradientBoostingClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.08,
        subsample=0.8, min_samples_leaf=10, random_state=42,
    )),
])

cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cv_scores = cross_val_score(pipe, X, y, cv=cv, scoring="roc_auc")
print(f"5-fold CV ROC-AUC: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")

pipe.fit(X, y)
y_pred = pipe.predict(X)
y_prob = pipe.predict_proba(X)[:, 1]
train_acc = accuracy_score(y, y_pred)
auc = roc_auc_score(y, y_prob)
print(f"Train accuracy: {train_acc:.3f}  AUC: {auc:.3f}")
print(classification_report(y, y_pred, target_names=["normal", "failure"]))

# Feature importance
gbm = pipe.named_steps["gbm"]
for feat, imp in sorted(zip(FEATURE_COLS, gbm.feature_importances_), key=lambda x: -x[1]):
    print(f"  {feat:35s}  {imp:.4f}")

# COMMAND ----------
# ── MLflow logging + UC registration ───────────────────────────────────────────

if TOKEN:
    os.environ["DATABRICKS_HOST"]  = HOST
    os.environ["DATABRICKS_TOKEN"] = TOKEN
    mlflow.set_tracking_uri("databricks")
    mlflow.set_registry_uri("databricks-uc")
    try:
        mlflow.set_experiment(EXP_NAME)
    except Exception as e:
        print(f"Experiment warning: {e}")

sample_in  = pd.DataFrame(X[:4], columns=FEATURE_COLS)
sample_out = pipe.predict(X[:4])
signature  = infer_signature(sample_in, sample_out)

with mlflow.start_run(run_name="pdm-gbm-v1") as run:
    mlflow.log_params({
        "model_type":        "GradientBoosting",
        "n_estimators":      200,
        "max_depth":         4,
        "learning_rate":     0.08,
        "feature_dim":       len(FEATURE_COLS),
        "training_rows":     len(df),
        "machines":          len(MACHINES),
        "uc_table":          f"{CATALOG}.{SCHEMA}.{TABLE}",
    })
    mlflow.log_metrics({
        "cv_roc_auc_mean": round(float(cv_scores.mean()), 4),
        "cv_roc_auc_std":  round(float(cv_scores.std()),  4),
        "train_accuracy":  round(train_acc, 4),
        "train_roc_auc":   round(auc, 4),
    })

    model_info = mlflow.sklearn.log_model(
        pipe,
        artifact_path="model",
        signature=signature,
        input_example=sample_in,
        registered_model_name=MODEL_UC,
    )

    print(f"\nModel registered: {MODEL_UC}")
    print(f"Run ID: {run.info.run_id}")
    print(f"URI:    {model_info.model_uri}")

# COMMAND ----------
# ── Create / update Model Serving endpoint ─────────────────────────────────────

try:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.serving import (
        EndpointCoreConfigInput, ServedModelInput, ServedModelInputWorkloadSize,
    )
    import databricks.sdk.service.serving as serving_svc

    w = WorkspaceClient(host=HOST, token=TOKEN)

    # Get latest registered version
    versions = list(w.registered_models.list_versions(MODEL_UC))
    latest   = max(v.version for v in versions) if versions else "1"
    print(f"Latest model version: {latest}")

    served = ServedModelInput(
        name=f"pdm-v{latest}",
        model_name=MODEL_UC,
        model_version=str(latest),
        workload_size=ServedModelInputWorkloadSize.SMALL,
        scale_to_zero_enabled=True,
    )
    config = EndpointCoreConfigInput(served_models=[served])

    try:
        existing = w.serving_endpoints.get(ENDPOINT)
        w.serving_endpoints.update_config(name=ENDPOINT, served_models=[served])
        print(f"Updated endpoint: {ENDPOINT}")
    except Exception:
        w.serving_endpoints.create(name=ENDPOINT, config=config)
        print(f"Created endpoint: {ENDPOINT}")

    print(f"\nEndpoint URL: {HOST}/serving-endpoints/{ENDPOINT}/invocations")
    print(f"Set PDM_ENDPOINT={ENDPOINT} in app.yaml")

except ImportError:
    print("databricks-sdk not available — create endpoint manually:")
    print(f"  Model: {MODEL_UC}")
    print(f"  Endpoint name: {ENDPOINT}")
except Exception as e:
    print(f"Endpoint setup error (create manually): {e}")

# COMMAND ----------
print(f"""
{'='*60}
PDM Model Training Complete
{'='*60}
UC Table   : {CATALOG}.{SCHEMA}.{TABLE}
UC Model   : {MODEL_UC}
Endpoint   : {ENDPOINT}
Features   : {FEATURE_COLS}

Next steps:
  1. Set PDM_ENDPOINT={ENDPOINT} in databricks_mfg_app/app.yaml
  2. The /api/predict-maintenance endpoint will call it automatically
  3. The Maintenance tab in the app will show live risk scores
{'='*60}
""")
