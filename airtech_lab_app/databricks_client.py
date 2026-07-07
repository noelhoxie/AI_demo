"""Databricks SQL connector for bronze layer reads.

Reads raw machine data from Delta tables in the bronze layer.
Falls back to synthetic demo data when Databricks is not configured.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from typing import Any

import config

# Try to import the Databricks SQL connector
try:
    from databricks import sql as dbsql
    _HAS_DBSQL = True
except ImportError:
    _HAS_DBSQL = False


# ── Real Databricks client ─────────────────────────────────────────────────────

def _get_connection():
    if not _HAS_DBSQL:
        raise RuntimeError("databricks-sql-connector not installed")
    if not config.DATABRICKS_HOST or not config.DATABRICKS_TOKEN:
        raise RuntimeError("DATABRICKS_HOST / DATABRICKS_TOKEN not set")
    return dbsql.connect(
        server_hostname=config.DATABRICKS_HOST.replace("https://", ""),
        http_path=f"/sql/1.0/warehouses/{config.DATABRICKS_WAREHOUSE}",
        access_token=config.DATABRICKS_TOKEN,
    )


def _dbsql_query(sql: str, params: tuple = ()) -> list[dict]:
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


# ── Synthetic demo data ────────────────────────────────────────────────────────

_SERIAL_POOL = [f"ATC-{1000 + i}" for i in range(20)]
_MODEL_POOL  = ["P300-HPC", "P500-LPX", "F200-STD", "F400-PRO", "P100-ECO"]

def _demo_pressure_reading(idx: int, offset_hours: float = 0) -> dict:
    rng  = random.Random(idx * 17 + 3)
    ts   = datetime.utcnow() - timedelta(hours=offset_hours)
    psi  = round(rng.gauss(145, 12), 2)
    leak = round(max(0, rng.gauss(0.05, 0.03)), 4)
    return {
        "reading_id":       f"PR-{idx:05d}",
        "machine_id":       "machine_pressure",
        "serial_number":    rng.choice(_SERIAL_POOL),
        "model_number":     rng.choice(_MODEL_POOL[:3]),
        "test_type":        "leak_test",
        "pressure_psi":     psi,
        "hold_time_sec":    rng.choice([30, 60, 90]),
        "leak_rate_psi_min": leak,
        "ambient_temp_c":   round(rng.uniform(19, 25), 1),
        "result_raw":       "PASS" if (psi >= 130 and leak < 0.1) else "FAIL",
        "recorded_at":      ts.isoformat(),
        "source_table":     "machine_pressure_readings",
    }


def _demo_flow_reading(idx: int, offset_hours: float = 0) -> dict:
    rng  = random.Random(idx * 13 + 7)
    ts   = datetime.utcnow() - timedelta(hours=offset_hours)
    flow = round(rng.gauss(95, 8), 2)
    eff  = round(rng.uniform(78, 98), 1)
    return {
        "reading_id":       f"FR-{idx:05d}",
        "machine_id":       "machine_flow",
        "serial_number":    rng.choice(_SERIAL_POOL),
        "model_number":     rng.choice(_MODEL_POOL[2:]),
        "test_type":        "flow_performance",
        "flow_rate_lpm":    flow,
        "delta_p_bar":      round(rng.uniform(0.5, 2.5), 3),
        "efficiency_pct":   eff,
        "rpm":              rng.choice([1450, 1750, 2900, 3500]),
        "vibration_mm_s":   round(rng.uniform(0.5, 4.5), 2),
        "result_raw":       "PASS" if (flow >= 80 and eff >= 80) else "FAIL",
        "recorded_at":      ts.isoformat(),
        "source_table":     "machine_flow_readings",
    }


def _generate_demo_readings(machine_id: str, limit: int, offset: int) -> list[dict]:
    readings = []
    for i in range(limit):
        idx = offset + i
        hours_ago = idx * 0.5  # one reading every 30 min
        if machine_id == "machine_pressure":
            readings.append(_demo_pressure_reading(idx, hours_ago))
        else:
            readings.append(_demo_flow_reading(idx, hours_ago))
    return readings


# ── Public API ─────────────────────────────────────────────────────────────────

def get_readings(machine_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """Fetch raw readings from the bronze Delta table for a given machine."""
    machine = next((m for m in config.get_machines() if m["id"] == machine_id), None)
    if not machine:
        return []

    if not config.DATABRICKS_HOST or not _HAS_DBSQL:
        return _generate_demo_readings(machine_id, limit, offset)

    try:
        table = machine["table"]
        rows = _dbsql_query(
            f"SELECT * FROM {table} ORDER BY recorded_at DESC LIMIT {limit} OFFSET {offset}"
        )
        # Normalize: ensure machine_id field
        for r in rows:
            r.setdefault("machine_id", machine_id)
        return rows
    except Exception:
        return _generate_demo_readings(machine_id, limit, offset)


def get_reading(machine_id: str, reading_id: str) -> dict | None:
    """Fetch a single reading by ID."""
    machine = next((m for m in config.get_machines() if m["id"] == machine_id), None)
    if not machine:
        return None

    if not config.DATABRICKS_HOST or not _HAS_DBSQL:
        # Reconstruct from demo data (reading_id encodes the index)
        try:
            prefix  = "PR-" if machine_id == "machine_pressure" else "FR-"
            idx     = int(reading_id.replace(prefix, ""))
            hours   = idx * 0.5
            fn      = _demo_pressure_reading if machine_id == "machine_pressure" else _demo_flow_reading
            return fn(idx, hours)
        except Exception:
            return None

    try:
        table = machine["table"]
        rows = _dbsql_query(
            f"SELECT * FROM {table} WHERE reading_id = '{reading_id}' LIMIT 1"
        )
        if rows:
            rows[0].setdefault("machine_id", machine_id)
            return rows[0]
        return None
    except Exception:
        return None


def get_historical_stats(machine_id: str, test_type: str | None = None) -> dict:
    """Return historical pass/fail statistics for prediction context."""
    machine = next((m for m in config.get_machines() if m["id"] == machine_id), None)
    if not machine:
        return {}

    if not config.DATABRICKS_HOST or not _HAS_DBSQL:
        # Return synthetic stats
        rng = random.Random(hash(machine_id))
        total = rng.randint(400, 1200)
        passes = int(total * rng.uniform(0.72, 0.94))
        return {
            "machine_id":      machine_id,
            "test_type":       test_type,
            "total_readings":  total,
            "pass_count":      passes,
            "fail_count":      total - passes,
            "pass_rate_pct":   round(100 * passes / total, 1),
            "avg_cycle_min":   round(rng.uniform(18, 45), 1),
            "p95_cycle_min":   round(rng.uniform(55, 90), 1),
            "common_failures": ["seal_leak", "pressure_drop", "vibration_high"][:rng.randint(1, 3)],
        }

    try:
        table = machine["table"]
        where = f"WHERE test_type='{test_type}'" if test_type else ""
        rows = _dbsql_query(f"""
            SELECT
                COUNT(*) AS total_readings,
                SUM(CASE WHEN result_raw='PASS' THEN 1 ELSE 0 END) AS pass_count,
                SUM(CASE WHEN result_raw='FAIL' THEN 1 ELSE 0 END) AS fail_count,
                ROUND(100.0 * SUM(CASE WHEN result_raw='PASS' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pass_rate_pct
            FROM {table} {where}
        """)
        return rows[0] if rows else {}
    except Exception:
        return {}
