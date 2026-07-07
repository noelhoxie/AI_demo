"""Airtech Lab Intelligence Platform — Flask API"""
import json
import os
import threading
import random as _rnd
from datetime import datetime, date, timedelta
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import config
import databricks_client as dbc
from db import run_query, run_write

# ── Flask setup ────────────────────────────────────────────────────────────────
STATIC_DIR = Path(__file__).parent / "frontend" / "dist"
app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="")


# ── Lakebase schema auto-init ──────────────────────────────────────────────────
def _init_schema():
    """Idempotently create the lab.* tables in Lakebase on first startup."""
    ddl_statements = [
        "CREATE SCHEMA IF NOT EXISTS lab",
        # ── Inspection master data ──
        """CREATE TABLE IF NOT EXISTS lab.insp_master (
            key        VARCHAR(50) PRIMARY KEY,
            items      JSONB       NOT NULL DEFAULT '[]'
        )""",
        # ── Inspection records (header) ──
        """CREATE TABLE IF NOT EXISTS lab.inspection_records (
            id               SERIAL PRIMARY KEY,
            product          VARCHAR(200),
            wo_number        VARCHAR(100),
            inspection_date  DATE,
            part_number      VARCHAR(100),
            serial_number    VARCHAR(100),
            operation        VARCHAR(100),
            equipment        VARCHAR(200),
            machinist        VARCHAR(100),
            tool_change      JSONB DEFAULT '{}',
            status           VARCHAR(20) DEFAULT 'in_progress',
            created_at       TIMESTAMP DEFAULT NOW(),
            updated_at       TIMESTAMP DEFAULT NOW()
        )""",
        # ── Inspection rows (measurements) ──
        """CREATE TABLE IF NOT EXISTS lab.inspection_rows (
            id              SERIAL PRIMARY KEY,
            record_id       INTEGER REFERENCES lab.inspection_records(id) ON DELETE CASCADE,
            row_number      INTEGER NOT NULL,
            char_designator VARCHAR(100),
            requirement     VARCHAR(200),
            tool            VARCHAR(100),
            sample_rate     VARCHAR(50),
            piece_1st       VARCHAR(20),
            piece_5th       VARCHAR(20),
            piece_10th      VARCHAR(20),
            piece_15th      VARCHAR(20),
            piece_20th      VARCHAR(20),
            piece_25th      VARCHAR(20),
            piece_30th      VARCHAR(20),
            piece_35th      VARCHAR(20),
            piece_iqa       VARCHAR(20),
            sn_values       JSONB DEFAULT '[]',
            created_at      TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS idx_insp_rows_record ON lab.inspection_rows (record_id)",
        # ── Work order catalog ──
        """CREATE TABLE IF NOT EXISTS lab.wo_catalog (
            id          SERIAL PRIMARY KEY,
            wo_number   VARCHAR(50)  UNIQUE NOT NULL,
            product     VARCHAR(200) NOT NULL,
            part_number VARCHAR(100),
            description TEXT,
            is_active   BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMP DEFAULT NOW(),
            updated_at  TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS idx_wo_active ON lab.wo_catalog (is_active)",
        # ── Inspection templates ──
        """CREATE TABLE IF NOT EXISTS lab.insp_templates (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(200) NOT NULL,
            product     VARCHAR(200),
            part_number VARCHAR(100),
            description TEXT,
            operation   VARCHAR(100),
            is_active   BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMP DEFAULT NOW(),
            updated_at  TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS lab.insp_template_rows (
            id              SERIAL PRIMARY KEY,
            template_id     INTEGER REFERENCES lab.insp_templates(id) ON DELETE CASCADE,
            row_number      INTEGER NOT NULL,
            char_designator VARCHAR(100),
            requirement     VARCHAR(200),
            tool            VARCHAR(100),
            sample_rate     VARCHAR(50)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_tmpl_rows ON lab.insp_template_rows (template_id)",
        # Seed default master data
        """INSERT INTO lab.insp_master (key, items) VALUES
            ('charDesignators', '["OD","ID","FLAT","//","TRUE","DIM","Major OD","Minor OD","Major ID","Minor ID","Roundness","Overall Height","Face Depth 1","Face Depth 2","Hole Diameter","THRD","O","TIR","VISUAL"]'),
            ('tools', '["Pins","Mics","Drop Gauge","T. Gauge","Dial Indicator","Verified by Machine Tool","Visual","Comparitor","Wires","Bore Mics","Thread Gauge","Calipers","Cannot Measure","Need to Define"]'),
            ('sampleRates', '["100%","Every 5th","None"]'),
            ('machinists', '["M. Kesel","R. Reid","T. Wagner","R. Appleton","M. Behrens"]'),
            ('adminPin', '"1234"')
           ON CONFLICT DO NOTHING""",
        """CREATE TABLE IF NOT EXISTS lab.technicians (
            id         SERIAL PRIMARY KEY,
            name       VARCHAR(100) NOT NULL,
            badge_id   VARCHAR(50)  UNIQUE,
            specialty  VARCHAR(100),
            email      VARCHAR(150),
            is_active  BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS lab.reading_enhancements (
            id                  SERIAL PRIMARY KEY,
            bronze_reading_id   VARCHAR(100) NOT NULL,
            machine_id          VARCHAR(100),
            technician_id       INTEGER REFERENCES lab.technicians(id),
            visual_inspection   TEXT,
            anomalies_noted     TEXT,
            corrective_actions  TEXT,
            override_values     JSONB DEFAULT '{}',
            manual_measurements JSONB DEFAULT '[]',
            confidence_in_data  INTEGER CHECK (confidence_in_data BETWEEN 1 AND 5),
            notes               TEXT,
            created_at          TIMESTAMP DEFAULT NOW(),
            updated_at          TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS idx_enh_rid ON lab.reading_enhancements (bronze_reading_id)",
        """CREATE TABLE IF NOT EXISTS lab.predictions (
            id                  SERIAL PRIMARY KEY,
            bronze_reading_id   VARCHAR(100) NOT NULL UNIQUE,
            machine_id          VARCHAR(100),
            success_probability NUMERIC(5,2),
            risk_level          VARCHAR(20),
            risk_factors        JSONB DEFAULT '[]',
            recommendations     JSONB DEFAULT '[]',
            reasoning           TEXT,
            model_version       VARCHAR(100),
            raw_response        TEXT,
            generated_at        TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS idx_pred_rid ON lab.predictions (bronze_reading_id)",
        """CREATE TABLE IF NOT EXISTS lab.test_schedule (
            id                     SERIAL PRIMARY KEY,
            title                  VARCHAR(200) NOT NULL,
            sample_id              VARCHAR(100),
            reading_id             VARCHAR(100),
            machine_id             VARCHAR(100),
            test_type              VARCHAR(100),
            scheduled_at           TIMESTAMP,
            estimated_duration_min INTEGER DEFAULT 60,
            priority               VARCHAR(20) DEFAULT 'normal'
                                       CHECK (priority IN ('critical','high','normal','low')),
            technician_id          INTEGER REFERENCES lab.technicians(id),
            status                 VARCHAR(30) DEFAULT 'scheduled'
                                       CHECK (status IN ('scheduled','in_progress','completed','cancelled')),
            started_at             TIMESTAMP,
            completed_at           TIMESTAMP,
            notes                  TEXT,
            created_at             TIMESTAMP DEFAULT NOW(),
            updated_at             TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS idx_sched_status ON lab.test_schedule (status, scheduled_at)",
        "CREATE INDEX IF NOT EXISTS idx_sched_tech ON lab.test_schedule (technician_id)",
        # Seed demo technicians (ignore conflicts)
        """INSERT INTO lab.technicians (name, badge_id, specialty, email) VALUES
            ('Marcus Webb',    'AT-101', 'Pressure & Leak Testing',  'mwebb@airtech.com'),
            ('Priya Nair',     'AT-102', 'Flow Performance Testing', 'pnair@airtech.com'),
            ('Carlos Fuentes', 'AT-103', 'Mechanical Inspection',    'cfuentes@airtech.com'),
            ('Dana Holloway',  'AT-104', 'Electrical & Vibration',   'dholloway@airtech.com'),
            ('James Okafor',   'AT-105', 'Final Acceptance Testing', 'jokafor@airtech.com')
           ON CONFLICT DO NOTHING""",
        # ── Test Procedure builder ──────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS lab.test_procedures (
            id           SERIAL PRIMARY KEY,
            name         VARCHAR(200) NOT NULL,
            doc_id       VARCHAR(100),
            version      VARCHAR(20),
            product_type VARCHAR(100),
            description  TEXT,
            is_active    BOOLEAN DEFAULT TRUE,
            created_at   TIMESTAMP DEFAULT NOW(),
            updated_at   TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS lab.test_proc_sections (
            id           SERIAL PRIMARY KEY,
            procedure_id INTEGER REFERENCES lab.test_procedures(id) ON DELETE CASCADE,
            order_index  INTEGER NOT NULL,
            title        VARCHAR(200) NOT NULL,
            section_type VARCHAR(30) DEFAULT 'manual'
                             CHECK (section_type IN ('manual','instruction','auto'))
        )""",
        "CREATE INDEX IF NOT EXISTS idx_proc_sects ON lab.test_proc_sections(procedure_id)",
        """CREATE TABLE IF NOT EXISTS lab.test_proc_steps (
            id              SERIAL PRIMARY KEY,
            section_id      INTEGER REFERENCES lab.test_proc_sections(id) ON DELETE CASCADE,
            order_index     INTEGER NOT NULL,
            step_type       VARCHAR(30) NOT NULL
                               CHECK (step_type IN ('instruction','text','radio','number',
                                                    'ok_check','pass_fail','auto_number')),
            label           TEXT NOT NULL,
            options_json    JSONB DEFAULT '[]',
            tolerances_json JSONB DEFAULT '{}',
            is_mandatory    BOOLEAN DEFAULT TRUE,
            is_critical     BOOLEAN DEFAULT FALSE,
            condition_json  JSONB DEFAULT NULL,
            hint_text       TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_proc_steps ON lab.test_proc_steps(section_id)",
        """CREATE TABLE IF NOT EXISTS lab.test_runs (
            id              SERIAL PRIMARY KEY,
            procedure_id    INTEGER REFERENCES lab.test_procedures(id),
            serial_number   VARCHAR(100),
            model_number    VARCHAR(100),
            test_location   VARCHAR(100),
            technician_name VARCHAR(100),
            status          VARCHAR(20) DEFAULT 'in_progress'
                               CHECK (status IN ('in_progress','completed','failed')),
            created_at      TIMESTAMP DEFAULT NOW(),
            updated_at      TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS idx_runs_proc ON lab.test_runs(procedure_id)",
        """CREATE TABLE IF NOT EXISTS lab.test_run_responses (
            id              SERIAL PRIMARY KEY,
            run_id          INTEGER REFERENCES lab.test_runs(id) ON DELETE CASCADE,
            step_id         INTEGER REFERENCES lab.test_proc_steps(id),
            value           TEXT,
            auto_generated  BOOLEAN DEFAULT FALSE,
            passed          BOOLEAN,
            created_at      TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS idx_run_responses ON lab.test_run_responses(run_id)",
        # ── Test run images ────────────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS lab.test_run_images (
            id         SERIAL PRIMARY KEY,
            run_id     INTEGER REFERENCES lab.test_runs(id) ON DELETE CASCADE,
            step_id    INTEGER REFERENCES lab.test_proc_steps(id),
            filename   VARCHAR(255),
            mime_type  VARCHAR(100) DEFAULT 'image/jpeg',
            data_b64   TEXT NOT NULL,
            caption    TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS idx_run_images ON lab.test_run_images(run_id)",
        "ALTER TABLE lab.test_run_images ADD COLUMN IF NOT EXISTS section_id INTEGER REFERENCES lab.test_proc_sections(id)",
        # Reference images attached to procedure steps (shown as guides during test execution)
        """CREATE TABLE IF NOT EXISTS lab.test_proc_step_images (
            id          SERIAL PRIMARY KEY,
            step_id     INTEGER REFERENCES lab.test_proc_steps(id) ON DELETE CASCADE,
            filename    VARCHAR(255),
            mime_type   VARCHAR(100) DEFAULT 'image/jpeg',
            data_b64    TEXT NOT NULL,
            order_index INTEGER DEFAULT 0,
            created_at  TIMESTAMP DEFAULT NOW()
        )""",
        "CREATE INDEX IF NOT EXISTS idx_proc_step_images ON lab.test_proc_step_images(step_id)",
        # Allow 'photo' step type (drop old constraint, add new one)
        "ALTER TABLE lab.test_proc_steps DROP CONSTRAINT IF EXISTS test_proc_steps_step_type_check",
        """ALTER TABLE lab.test_proc_steps ADD CONSTRAINT test_proc_steps_step_type_check
           CHECK (step_type IN ('instruction','text','radio','number',
                                'ok_check','pass_fail','auto_number','photo'))""",
    ]
    try:
        for ddl in ddl_statements:
            run_write(ddl, returning=False)
        # Seed demo schedule if empty
        ok, rows = run_query("SELECT COUNT(*) AS cnt FROM lab.test_schedule")
        if ok and rows and rows[0]["cnt"] == 0:
            _seed_schedule()
        ok, rows = run_query("SELECT COUNT(*) AS cnt FROM lab.wo_catalog")
        if ok and rows and rows[0]["cnt"] == 0:
            _seed_wo_catalog()
        ok, rows = run_query("SELECT COUNT(*) AS cnt FROM lab.insp_templates")
        if ok and rows and rows[0]["cnt"] == 0:
            _seed_templates()
        ok, rows = run_query("SELECT COUNT(*) AS cnt FROM lab.inspection_records")
        if ok and rows and rows[0]["cnt"] == 0:
            _seed_inspection_records()
        # Ensure dense recent data — reseed if fewer than 30 records exist in the last 30 days
        ok, rows = run_query(
            "SELECT COUNT(*) AS cnt FROM lab.inspection_records "
            "WHERE inspection_date >= CURRENT_DATE - INTERVAL '30 days'"
        )
        if ok and rows and rows[0]["cnt"] < 30:
            _seed_recent_inspection_data()
        ok, rows = run_query("SELECT COUNT(*) AS cnt FROM lab.test_procedures")
        if ok and rows and rows[0]["cnt"] == 0:
            _seed_rook2_procedure()
        ok, rows = run_query("SELECT COUNT(*) AS cnt FROM lab.test_runs")
        if ok and rows and rows[0]["cnt"] == 0:
            _seed_demo_test_runs()
        # Backfill responses for any runs that have none (handles existing seeded data)
        ok, runs_without = run_query("""
            SELECT r.id, r.procedure_id, r.status
            FROM lab.test_runs r
            WHERE NOT EXISTS (
                SELECT 1 FROM lab.test_run_responses rr WHERE rr.run_id = r.id
            )
            LIMIT 300
        """)
        if ok and runs_without:
            for run in runs_without:
                _generate_run_responses(run["id"], run["procedure_id"], run["status"])
    except Exception as e:
        app.logger.warning(f"Schema init skipped (DB may not be ready): {e}")


def _seed_schedule():
    seeds = [
        ("Leak Test — P300-HPC SN-1042",    "SN-1042", "machine_pressure", "leak_test",       10,  45, "critical", "AT-101"),
        ("Flow Perf — F200-STD SN-2071",    "SN-2071", "machine_flow",     "flow_performance", 25,  60, "high",     "AT-102"),
        ("Pressure Test — P500-LPX SN-1088","SN-1088", "machine_pressure", "pressure_test",    60,  30, "normal",   "AT-101"),
        ("Vibration — F400-PRO SN-2099",    "SN-2099", "machine_flow",     "vibration_test",   90,  45, "high",     "AT-104"),
        ("Leak Test — P100-ECO SN-1055",    "SN-1055", "machine_pressure", "leak_test",        120, 45, "normal",   "AT-103"),
        ("Final Accept — P300-HPC SN-1019", "SN-1019", "machine_pressure", "acceptance",       150, 90, "critical", "AT-105"),
        ("Flow Perf — F200-STD SN-2034",    "SN-2034", "machine_flow",     "flow_performance", 180, 60, "normal",   "AT-102"),
        ("Pressure Test — P500-LPX SN-1077","SN-1077", "machine_pressure", "pressure_test",    210, 30, "low",      "AT-103"),
        ("Vibration — F400-PRO SN-2088",    "SN-2088", "machine_flow",     "vibration_test",   240, 45, "normal",   "AT-104"),
        ("Final Accept — F200-STD SN-2012", "SN-2012", "machine_flow",     "acceptance",       270, 90, "high",     "AT-105"),
    ]
    for title, sample, machine, test_type, offset_min, dur, priority, badge in seeds:
        ok, rows = run_query(
            "SELECT id FROM lab.technicians WHERE badge_id=%s LIMIT 1", (badge,)
        )
        tech_id = rows[0]["id"] if ok and rows else None
        run_write(
            """INSERT INTO lab.test_schedule
               (title, sample_id, machine_id, test_type, scheduled_at,
                estimated_duration_min, priority, technician_id)
               VALUES (%s,%s,%s,%s, NOW() + (%s * INTERVAL '1 minute'),%s,%s,%s)""",
            (title, sample, machine, test_type, offset_min, dur, priority, tech_id),
            returning=False,
        )


def _seed_wo_catalog():
    seeds = [
        ("WO-2025-1001", "HOUSING, 5X",          "AT-10051"),
        ("WO-2025-1002", "HOUSING, 6X",          "AT-10061"),
        ("WO-2025-1003", "HOUSING, 8X",          "AT-10082"),
        ("WO-2025-1004", "IMPELLER, TYPE-A",     "AT-20011"),
        ("WO-2025-1005", "IMPELLER, TYPE-B",     "AT-20012"),
        ("WO-2025-1006", "VALVE BODY, 1/2\"",    "AT-30051"),
        ("WO-2025-1007", "VALVE BODY, 3/4\"",    "AT-30075"),
        ("WO-2025-1008", "MANIFOLD, 4-PORT",     "AT-40041"),
        ("WO-2025-1009", "MANIFOLD, 6-PORT",     "AT-40061"),
        ("WO-2025-1010", "CYLINDER, 2\" BORE",   "AT-50020"),
        ("WO-2025-1011", "CYLINDER, 3\" BORE",   "AT-50030"),
        ("WO-2025-1012", "SHAFT, 12mm",          "AT-60012"),
        ("WO-2025-1013", "SHAFT, 16mm",          "AT-60016"),
        ("WO-2025-1014", "BEARING HOUSING, SM",  "AT-70010"),
        ("WO-2025-1015", "BEARING HOUSING, LG",  "AT-70020"),
        ("WO-2025-1016", "ROTOR, TYPE-A",        "AT-80011"),
        ("WO-2025-1017", "ROTOR, TYPE-B",        "AT-80012"),
        ("WO-2025-1018", "END CAP, HEX",         "AT-90010"),
        ("WO-2025-1019", "END CAP, ROUND",       "AT-90020"),
        ("WO-2025-1020", "PORT BLOCK, 3/4\" NPT","AT-11010"),
        ("WO-2025-1021", "PORT BLOCK, 1\" NPT",  "AT-11020"),
        ("WO-2025-1022", "PISTON, 40mm",         "AT-12040"),
        ("WO-2025-1023", "PISTON, 50mm",         "AT-12050"),
        ("WO-2025-1024", "BODY, REGULATOR",      "AT-13001"),
        ("WO-2025-1025", "BODY, SEPARATOR",      "AT-13002"),
        ("WO-2025-1026", "COVER, INLET",         "AT-14010"),
        ("WO-2025-1027", "COVER, OUTLET",        "AT-14020"),
        ("WO-2025-1028", "BRACKET, MTG-A",       "AT-15011"),
        ("WO-2025-1029", "PISTON ROD, 20mm",     "AT-16020"),
        ("WO-2025-1030", "ADAPTER, 1/2\" NPT",   "AT-16050"),
    ]
    for wo, product, part_no in seeds:
        run_write(
            "INSERT INTO lab.wo_catalog (wo_number, product, part_number) "
            "VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
            (wo, product, part_no), returning=False,
        )


def _seed_templates():
    template_data = [
        {
            "name": "Housing 5X — Final Inspection",
            "product": "HOUSING, 5X", "part_number": "AT-10051",
            "description": "Standard final inspection for 5X series housing",
            "operation": "Final Inspection",
            "rows": [
                (1,  "OD",            "3.750 \u00b10.001",                    "Mics",           "100%"),
                (2,  "ID",            "2.500 +0.0005/-0.0000",               "Bore Mics",      "100%"),
                (3,  "FLAT",          "0.0005 max",                           "Dial Indicator", "Every 5th"),
                (4,  "TIR",           "0.002 max",                            "Dial Indicator", "Every 5th"),
                (5,  "Overall Height","4.125 \u00b10.002",                    "Mics",           "100%"),
                (6,  "Face Depth 1",  "0.375 \u00b10.001",                    "Drop Gauge",     "100%"),
                (7,  "THRD",          "1/4-20 UNC-2B",                        "Thread Gauge",   "100%"),
                (8,  "VISUAL",        "No burrs, nicks, or sharp edges",      "Visual",         "100%"),
            ],
        },
        {
            "name": "Housing 6X — Final Inspection",
            "product": "HOUSING, 6X", "part_number": "AT-10061",
            "description": "Standard final inspection for 6X series housing",
            "operation": "Final Inspection",
            "rows": [
                (1,  "OD",            "4.500 \u00b10.001",                    "Mics",           "100%"),
                (2,  "ID",            "3.000 +0.0005/-0.0000",               "Bore Mics",      "100%"),
                (3,  "FLAT",          "0.0005 max",                           "Dial Indicator", "Every 5th"),
                (4,  "TIR",           "0.002 max",                            "Dial Indicator", "Every 5th"),
                (5,  "Overall Height","5.250 \u00b10.002",                    "Mics",           "100%"),
                (6,  "Face Depth 1",  "0.500 \u00b10.001",                    "Drop Gauge",     "100%"),
                (7,  "Face Depth 2",  "0.250 \u00b10.001",                    "Drop Gauge",     "100%"),
                (8,  "THRD",          "3/8-16 UNC-2B",                        "Thread Gauge",   "100%"),
                (9,  "VISUAL",        "No burrs, nicks, or sharp edges",      "Visual",         "100%"),
            ],
        },
        {
            "name": "Housing 8X — Final Inspection",
            "product": "HOUSING, 8X", "part_number": "AT-10082",
            "description": "Standard final inspection for 8X series housing",
            "operation": "Final Inspection",
            "rows": [
                (1,  "OD",            "5.875 \u00b10.001",                    "Mics",           "100%"),
                (2,  "ID",            "4.000 +0.0005/-0.0000",               "Bore Mics",      "100%"),
                (3,  "Minor OD",      "5.750 \u00b10.001",                    "Mics",           "100%"),
                (4,  "FLAT",          "0.0005 max",                           "Dial Indicator", "Every 5th"),
                (5,  "TIR",           "0.002 max",                            "Dial Indicator", "Every 5th"),
                (6,  "Overall Height","6.375 \u00b10.002",                    "Mics",           "100%"),
                (7,  "Face Depth 1",  "0.625 \u00b10.001",                    "Drop Gauge",     "100%"),
                (8,  "Face Depth 2",  "0.375 \u00b10.001",                    "Drop Gauge",     "100%"),
                (9,  "THRD",          "1/2-13 UNC-2B",                        "Thread Gauge",   "100%"),
                (10, "VISUAL",        "No burrs, nicks, or sharp edges",      "Visual",         "100%"),
            ],
        },
        {
            "name": "Shaft 12mm — Final Inspection",
            "product": "SHAFT, 12mm", "part_number": "AT-60012",
            "description": "Standard final inspection for 12mm precision shaft",
            "operation": "Final Inspection",
            "rows": [
                (1, "OD",            "12.000 -0.000/-0.009",                 "Mics",           "100%"),
                (2, "//",            "0.0005 max TIR",                        "Dial Indicator", "100%"),
                (3, "TRUE",          "0.001 max",                             "Dial Indicator", "Every 5th"),
                (4, "Overall Height","125.00 \u00b10.10",                     "Mics",           "Every 5th"),
                (5, "VISUAL",        "No burrs, Ra 1.6 \u03bcm max",         "Visual",         "100%"),
            ],
        },
        {
            "name": "Shaft 16mm — Final Inspection",
            "product": "SHAFT, 16mm", "part_number": "AT-60016",
            "description": "Standard final inspection for 16mm precision shaft",
            "operation": "Final Inspection",
            "rows": [
                (1, "OD",            "16.000 -0.000/-0.011",                 "Mics",           "100%"),
                (2, "//",            "0.0005 max TIR",                        "Dial Indicator", "100%"),
                (3, "TRUE",          "0.001 max",                             "Dial Indicator", "Every 5th"),
                (4, "Overall Height","150.00 \u00b10.10",                     "Mics",           "Every 5th"),
                (5, "VISUAL",        "No burrs, Ra 1.6 \u03bcm max",         "Visual",         "100%"),
            ],
        },
    ]
    for t in template_data:
        ok, tmpl = run_write(
            """INSERT INTO lab.insp_templates (name, product, part_number, description, operation)
               VALUES (%s,%s,%s,%s,%s) RETURNING id""",
            (t["name"], t["product"], t["part_number"], t["description"], t["operation"]),
        )
        if not ok:
            continue
        tid = tmpl["id"]
        for rn, cd, req, tool, sr in t["rows"]:
            run_write(
                """INSERT INTO lab.insp_template_rows
                   (template_id, row_number, char_designator, requirement, tool, sample_rate)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (tid, rn, cd, req, tool, sr), returning=False,
            )


def _seed_inspection_records():
    """Seed 100 demo inspection records with realistic pass/fail data."""
    _rnd.seed(42)
    products = [
        ("HOUSING, 5X",     "AT-10051", "WO-2025-1001"),
        ("HOUSING, 6X",     "AT-10061", "WO-2025-1002"),
        ("HOUSING, 8X",     "AT-10082", "WO-2025-1003"),
        ("SHAFT, 12mm",     "AT-60012", "WO-2025-1012"),
        ("SHAFT, 16mm",     "AT-60016", "WO-2025-1013"),
        ("IMPELLER, TYPE-A","AT-20011", "WO-2025-1004"),
        ('VALVE BODY, 1/2"',"AT-30051", "WO-2025-1006"),
        ("MANIFOLD, 4-PORT","AT-40041", "WO-2025-1008"),
        ("PISTON, 40mm",    "AT-12040", "WO-2025-1022"),
        ("ROTOR, TYPE-A",   "AT-80011", "WO-2025-1016"),
    ]
    weights   = [22, 15, 10, 13, 10, 9, 8, 7, 4, 2]
    machinists = ["M. Kesel", "R. Reid", "T. Wagner", "R. Appleton", "M. Behrens"]
    operations = ["Final Inspection", "In-Process Inspection", "First Article Inspection"]
    op_w       = [60, 30, 10]
    equipment_pool = ["HAAS VF-2", "HAAS ST-10", "Mazak QT-350", "DMG MORI NLX 2500", None, None]

    row_tmpl = {
        "HOUSING, 5X": [
            ("OD",            "3.750 \u00b10.001",           "Mics",           "100%"),
            ("ID",            "2.500 +0.0005/-0.0000",       "Bore Mics",      "100%"),
            ("FLAT",          "0.0005 max",                   "Dial Indicator", "Every 5th"),
            ("TIR",           "0.002 max",                    "Dial Indicator", "Every 5th"),
            ("Overall Height","4.125 \u00b10.002",            "Mics",           "100%"),
            ("THRD",          "1/4-20 UNC-2B",                "Thread Gauge",   "100%"),
            ("VISUAL",        "No burrs, nicks",              "Visual",         "100%"),
        ],
        "HOUSING, 6X": [
            ("OD",            "4.500 \u00b10.001",           "Mics",           "100%"),
            ("ID",            "3.000 +0.0005/-0.0000",       "Bore Mics",      "100%"),
            ("FLAT",          "0.0005 max",                   "Dial Indicator", "Every 5th"),
            ("TIR",           "0.002 max",                    "Dial Indicator", "Every 5th"),
            ("Overall Height","5.250 \u00b10.002",            "Mics",           "100%"),
            ("Face Depth 1",  "0.500 \u00b10.001",            "Drop Gauge",     "100%"),
            ("THRD",          "3/8-16 UNC-2B",                "Thread Gauge",   "100%"),
            ("VISUAL",        "No burrs, nicks",              "Visual",         "100%"),
        ],
        "HOUSING, 8X": [
            ("OD",            "5.875 \u00b10.001",           "Mics",           "100%"),
            ("ID",            "4.000 +0.0005/-0.0000",       "Bore Mics",      "100%"),
            ("Minor OD",      "5.750 \u00b10.001",           "Mics",           "100%"),
            ("FLAT",          "0.0005 max",                   "Dial Indicator", "Every 5th"),
            ("TIR",           "0.002 max",                    "Dial Indicator", "Every 5th"),
            ("Overall Height","6.375 \u00b10.002",            "Mics",           "100%"),
            ("THRD",          "1/2-13 UNC-2B",                "Thread Gauge",   "100%"),
            ("VISUAL",        "No burrs, nicks",              "Visual",         "100%"),
        ],
        "SHAFT, 12mm": [
            ("OD",            "12.000 -0.000/-0.009",        "Mics",           "100%"),
            ("//",            "0.0005 max TIR",               "Dial Indicator", "100%"),
            ("TRUE",          "0.001 max",                    "Dial Indicator", "Every 5th"),
            ("Overall Height","125.00 \u00b10.10",            "Mics",           "Every 5th"),
            ("VISUAL",        "No burrs",                     "Visual",         "100%"),
        ],
        "SHAFT, 16mm": [
            ("OD",            "16.000 -0.000/-0.011",        "Mics",           "100%"),
            ("//",            "0.0005 max TIR",               "Dial Indicator", "100%"),
            ("TRUE",          "0.001 max",                    "Dial Indicator", "Every 5th"),
            ("Overall Height","150.00 \u00b10.10",            "Mics",           "Every 5th"),
            ("VISUAL",        "No burrs",                     "Visual",         "100%"),
        ],
        "IMPELLER, TYPE-A": [
            ("OD",            "6.250 \u00b10.002",           "Mics",           "100%"),
            ("ID",            "1.500 \u00b10.0005",          "Bore Mics",      "100%"),
            ("FLAT",          "0.001 max",                    "Dial Indicator", "100%"),
            ("Roundness",     "0.001 max",                    "Dial Indicator", "Every 5th"),
            ("VISUAL",        "No burrs, balanced",           "Visual",         "100%"),
        ],
        'VALVE BODY, 1/2"': [
            ("OD",            "1.250 \u00b10.001",           "Mics",           "100%"),
            ("ID",            "0.500 +0.001/-0.000",         "Bore Mics",      "100%"),
            ("THRD",          "1/2-14 NPT",                   "Thread Gauge",   "100%"),
            ("VISUAL",        "No porosity, burrs",           "Visual",         "100%"),
        ],
        "MANIFOLD, 4-PORT": [
            ("OD",            "2.000 \u00b10.001",           "Mics",           "100%"),
            ("Hole Diameter", "0.500 \u00b10.001",           "Bore Mics",      "100%"),
            ("FLAT",          "0.001 max",                    "Dial Indicator", "Every 5th"),
            ("THRD",          "1/4-18 NPT",                   "Thread Gauge",   "100%"),
            ("VISUAL",        "No porosity, burrs",           "Visual",         "100%"),
        ],
        "PISTON, 40mm": [
            ("OD",            "40.000 -0.000/-0.010",        "Mics",           "100%"),
            ("//",            "0.0005 max",                   "Dial Indicator", "100%"),
            ("Overall Height","50.00 \u00b10.05",             "Mics",           "100%"),
            ("VISUAL",        "No scratches, burrs",          "Visual",         "100%"),
        ],
        "ROTOR, TYPE-A": [
            ("OD",            "4.875 \u00b10.001",           "Mics",           "100%"),
            ("ID",            "1.000 \u00b10.0005",          "Bore Mics",      "100%"),
            ("FLAT",          "0.0005 max",                   "Dial Indicator", "100%"),
            ("Roundness",     "0.001 max",                    "Dial Indicator", "Every 5th"),
            ("VISUAL",        "No burrs, balanced",           "Visual",         "100%"),
        ],
    }

    selected = _rnd.choices(products, weights=weights, k=100)
    for product, part_no, wo_no in selected:
        machinist = _rnd.choice(machinists)
        operation = _rnd.choices(operations, weights=op_w)[0]
        equipment = _rnd.choice(equipment_pool)
        days_ago  = _rnd.randint(0, 59)
        insp_date = (date.today() - timedelta(days=days_ago)).isoformat()
        is_fail   = _rnd.random() < 0.15

        ok, rec = run_write(
            """INSERT INTO lab.inspection_records
               (product, wo_number, inspection_date, part_number,
                operation, equipment, machinist, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'complete') RETURNING id""",
            (product, wo_no, insp_date, part_no, operation, equipment, machinist),
        )
        if not ok:
            continue
        rec_id   = rec["id"]
        rows     = row_tmpl.get(product, [("VISUAL", "See drawing", "Visual", "100%")])
        fail_idx = _rnd.randint(0, len(rows) - 1) if is_fail else -1
        for j, (char, req, tool, sr) in enumerate(rows):
            run_write(
                """INSERT INTO lab.inspection_rows
                   (record_id, row_number, char_designator, requirement,
                    tool, sample_rate, piece_1st)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (rec_id, j + 1, char, req, tool, sr, "Fail" if j == fail_idx else "Pass"),
                returning=False,
            )


def _seed_recent_inspection_data():
    """Seed 5-9 inspection records per day for the past 30 days with today-relative dates."""
    _rnd.seed(66)
    products = [
        ("HOUSING, 5X",     "AT-10051", "WO-2025-1001"),
        ("HOUSING, 6X",     "AT-10061", "WO-2025-1002"),
        ("HOUSING, 8X",     "AT-10082", "WO-2025-1003"),
        ("SHAFT, 12mm",     "AT-60012", "WO-2025-1012"),
        ("SHAFT, 16mm",     "AT-60016", "WO-2025-1013"),
        ("IMPELLER, TYPE-A","AT-20011", "WO-2025-1004"),
        ('VALVE BODY, 1/2"',"AT-30051", "WO-2025-1006"),
        ("MANIFOLD, 4-PORT","AT-40041", "WO-2025-1008"),
        ("PISTON, 40mm",    "AT-12040", "WO-2025-1022"),
        ("ROTOR, TYPE-A",   "AT-80011", "WO-2025-1016"),
    ]
    weights    = [22, 15, 10, 13, 10, 9, 8, 7, 4, 2]
    machinists = ["M. Kesel", "R. Reid", "T. Wagner", "R. Appleton", "M. Behrens"]
    operations = ["Final Inspection", "In-Process Inspection", "First Article Inspection"]
    op_w       = [60, 30, 10]
    equipment_pool = ["HAAS VF-2", "HAAS ST-10", "Mazak QT-350", "DMG MORI NLX 2500", None, None]

    today = date.today()
    for days_ago in range(30, 0, -1):
        day = today - timedelta(days=days_ago)
        daily_count = _rnd.randint(5, 9)
        selected = _rnd.choices(products, weights=weights, k=daily_count)
        for product, part_no, wo_no in selected:
            machinist = _rnd.choice(machinists)
            operation = _rnd.choices(operations, weights=op_w)[0]
            equipment = _rnd.choice(equipment_pool)
            is_fail   = _rnd.random() < 0.15
            ok, rec = run_write(
                """INSERT INTO lab.inspection_records
                   (product, wo_number, inspection_date, part_number,
                    operation, equipment, machinist, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,'complete') RETURNING id""",
                (product, wo_no, day.isoformat(), part_no, operation, equipment, machinist),
            )
            if not ok:
                continue
            run_write(
                """INSERT INTO lab.inspection_rows
                   (record_id, row_number, char_designator, requirement,
                    tool, sample_rate, piece_1st)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (rec["id"], 1, "OD", "See drawing", "Mics", "100%",
                 "Fail" if is_fail else "Pass"),
                returning=False,
            )


def _seed_rook2_procedure():
    """Seed the Rook2 blower test procedure from QA-WI-148."""
    ok, proc = run_write(
        """INSERT INTO lab.test_procedures (name, doc_id, version, product_type, description)
           VALUES (%s,%s,%s,%s,%s) RETURNING id""",
        ("Rook2 Blower Test Record", "QA-WI-148", "3.6", "rook2",
         "Rook2 Testing: FBL / Phoenix FBL / ROOK2-R (Rework) / Rook2-RL Blower Test Record"),
    )
    if not ok:
        return
    pid = proc["id"]

    def _sec(title, stype, idx):
        ok2, s = run_write(
            "INSERT INTO lab.test_proc_sections (procedure_id, order_index, title, section_type) "
            "VALUES (%s,%s,%s,%s) RETURNING id",
            (pid, idx, title, stype),
        )
        return s["id"] if ok2 else None

    def _step(sid, idx, stype, label, options=None, tol=None, mandatory=True, critical=False, cond=None, hint=None):
        ok3, s = run_write(
            """INSERT INTO lab.test_proc_steps
               (section_id, order_index, step_type, label, options_json, tolerances_json,
                is_mandatory, is_critical, condition_json, hint_text)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (sid, idx, stype, label,
             json.dumps(options or []), json.dumps(tol or {}),
             mandatory, critical,
             json.dumps(cond) if cond else None, hint),
        )
        return s["id"] if ok3 else None

    # ── Section 1: Pre-Test Inspection ────────────────────────────────────────
    s1 = _sec("Pre-Test Inspection", "manual", 1)
    if not s1:
        return
    _step(s1, 1, "radio", "Select the Blower Model Number on the label",
          options=["122927","122927-R","122927-R1","122927-R2","122927-RL",
                   "154095","154095-R","154095-RL","None of the above, call testing supervisor"])
    _step(s1, 2, "text",  "Serial Number: Use a barcode scanner",
          hint="Scan or manually enter the unit serial number")
    _step(s1, 3, "text",  "Test Location")
    _step(s1, 4, "ok_check", "Confirm that all external hardware is present")
    _step(s1, 5, "ok_check", "Perform Tug test on cable connector")
    _step(s1, 6, "ok_check", "Confirm no cracks, dents, or other visible defects are present")
    _step(s1, 7, "ok_check", "Confirm the blue tag is present")
    _step(s1, 8, "instruction",
          "Record the Motor Bearing information from the BLUE tag. "
          "(Example: '.000' = Shaft size. Enter '12.000' in the field below.)",
          mandatory=False)
    _step(s1, 9,  "number", "FRONT: Motor Front (MF) Shaft Size",
          tol={"nominal": 12.003, "lower": 12.0, "upper": 12.006, "unit": "mm"})
    _step(s1, 10, "radio",  "FRONT: Select Motor Front (MF) Bearing Manufacturer",
          options=["GRW","HQW","Not available"])
    _step(s1, 11, "number", "REAR: Motor Rear (MR) Shaft Size",
          tol={"nominal": 12.003, "lower": 12.0, "upper": 12.006, "unit": "mm"})
    rear_mfr_id = _step(s1, 12, "radio", "REAR: Select Motor Rear (MR) Bearing Manufacturer",
          options=["GRW","HQW","Not available"])
    _step(s1, 13, "number", "Motor Rear (MR) Bearing Radial Clearance (GRW)",
          tol={"nominal": 13, "lower": 11, "upper": 16, "unit": "\u00b5m"},
          cond={"step_id": rear_mfr_id, "value": "GRW"} if rear_mfr_id else None)
    _step(s1, 14, "number", "Test Pressure 7.5 PSI — Pressure Drop after 10 minutes",
          tol={"lower": 0.0, "upper": 0.1, "unit": "psi"},
          hint="Maximum allowable pressure drop: 0.1 psi over 10 minutes")

    # ── Section 2: Automated Performance Instructions ──────────────────────────
    s2 = _sec("Automated Performance Instructions", "instruction", 2)
    if not s2:
        return
    instructions = [
        'Ensure all alarms are cleared prior to starting the test procedure by clicking the "Alarms" button, then the "X" button. If alarms will not clear, contact the production supervisor.',
        "Ensure the fixture is clear of obstruction and debris. Confirm that both o-rings are installed and in good condition.",
        "Install the blower into the fixture as shown, ensuring the studs enter the slots and the unit sits flat against the bottom o-ring.",
        "Plug the unit's power cord into the station and ensure it is latched.",
        'Press "STOP" and then "RESET" before each test cycle.',
        "Using the barcode scanner, scan the station QR codes and blower serial numbers to register them in the system:\n1) Scan a station QR code\n2) Scan the serial number of the blower at that station\n3) The station will turn green on the HMI and display the scanned serial number\nRepeat for all blowers.",
        'Confirm that all relevant stations are highlighted in GREEN after scanning. Ensure that the "BREAK-IN ACTIVATE" and "HIGH TEMP ACTIVATE" buttons are activated and highlighted in GREEN before continuing.',
        'Automated Test (Bearing Break-In & Orifice Test): Press "START" to begin. Test progress will be displayed in green on the left side of the HMI.',
        "Once the test is started, confirm that all stations have latched correctly:\n1) Outlet port extended\n2) Blower rotated & flush against outlet port\n3) Springs compressed",
    ]
    for i, text in enumerate(instructions, 1):
        _step(s2, i, "instruction", text, mandatory=False)

    # ── Section 3: Automated Performance Results ───────────────────────────────
    s3 = _sec("Automated Performance Results", "auto", 3)
    if not s3:
        return
    _step(s3, 1, "instruction",
          "Performance test data will automatically populate below: Captured at 240 Hz & 75\u00b0C.",
          mandatory=False)
    _step(s3, 2, "auto_number", "Differential Pressure",
          tol={"lower": 32.97, "upper": 41.0, "unit": ""}, critical=True)
    _step(s3, 3, "auto_number", "Power",
          tol={"lower": 170.0, "upper": 500.0, "unit": "W"}, critical=True)
    _step(s3, 4, "auto_number", "Flow Rate (SCFM)",
          tol={"lower": 22.0, "upper": 25.5, "unit": "SCFM"}, critical=True)
    _step(s3, 5, "auto_number", "Gas Stream Temperature",
          tol={"nominal": 60.0, "lower": 50.0, "upper": 75.0, "unit": "\u00b0C"})
    _step(s3, 6, "auto_number", "Station Number",
          tol={"lower": 1.0, "upper": 8.0, "unit": ""}, critical=True)
    _step(s3, 7, "auto_number", "Radial Vibration",
          tol={"lower": 0.0, "upper": 2.5, "unit": "mm/s"}, mandatory=False)
    _step(s3, 8, "auto_number", "Axial Vibration",
          tol={"lower": 0.0, "upper": 1.0, "unit": "mm/s"}, mandatory=False)

    # ── Section 4: Manual Noise and Vibration Testing ──────────────────────────
    s4 = _sec("Manual Noise and Vibration Testing", "manual", 4)
    if not s4:
        return
    _step(s4, 1, "instruction",
          'Noise Evaluation: Click the "MANUAL ACTIVATION" button. Click the sliding bar to activate the required station.',
          mandatory=False)
    _step(s4, 2, "instruction",
          'Select the blower to be run manually. Click "MANUAL OPERATION". Click "BLOWER LATCH" to secure the blower. '
          'Tap Freq. Scale to input the frequency manually and enter the desired test frequency. Repeat for all stations.',
          mandatory=False)
    _step(s4, 3, "pass_fail",
          "Allow the unit to run for 15 sec at 100 Hz. Listen for abnormalities.", critical=True)
    _step(s4, 4, "instruction",
          "Vibration Testing (Manual): Place the blower on the vibration test stand and connect the plug to the test VFD.",
          mandatory=False)
    _step(s4, 5, "instruction",
          "Install the magnetic disc on the rear of the motor as shown. Attach the magnetic vibration probe. "
          "Run the unit at 12,000 RPM and record axial vibration.",
          mandatory=False)
    _step(s4, 6, "number", "Axial Vibration",
          tol={"lower": 0.0, "upper": 1.0, "unit": "mm/s"}, critical=True)
    _step(s4, 7, "instruction",
          "Install the radial vibration clamp on the ear of the volute, snug the thumb screws finger tight. "
          "Attach the vibration probe. Run the unit at 12,000 RPM and record radial vibration.",
          mandatory=False)
    _step(s4, 8, "number", "Record Radial Vibration values here.",
          tol={"nominal": 2.5, "lower": 0.0, "upper": 2.5, "unit": "mm/s"}, critical=True)


def _seed_procedure(name, doc_id, version, product_type, description, sections):
    """Generic helper to insert a procedure with sections and steps."""
    ok, proc = run_write(
        """INSERT INTO lab.test_procedures (name, doc_id, version, product_type, description)
           VALUES (%s,%s,%s,%s,%s) RETURNING id""",
        (name, doc_id, version, product_type, description),
    )
    if not ok:
        return
    pid = proc["id"]
    for si, sec in enumerate(sections, 1):
        ok2, sr = run_write(
            "INSERT INTO lab.test_proc_sections (procedure_id, order_index, title, section_type) "
            "VALUES (%s,%s,%s,%s) RETURNING id",
            (pid, si, sec["title"], sec["type"]),
        )
        if not ok2:
            continue
        sid = sr["id"]
        for ji, step in enumerate(sec["steps"], 1):
            run_write(
                """INSERT INTO lab.test_proc_steps
                   (section_id, order_index, step_type, label, options_json,
                    tolerances_json, is_mandatory, is_critical, hint_text)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (sid, ji, step["type"], step["label"],
                 json.dumps(step.get("options", [])),
                 json.dumps(step.get("tol", {})),
                 step.get("mandatory", True), step.get("critical", False),
                 step.get("hint")),
                returning=False,
            )


def _seed_fbl_procedure():
    _seed_procedure(
        "FBL Blower Performance Test", "QA-WI-155", "2.1", "fbl",
        "FBL / Phoenix FBL series blower performance and acceptance test",
        [
            {"title": "Pre-Test Setup", "type": "instruction", "steps": [
                {"type": "instruction", "label": "Read and understand test procedure fully before proceeding.", "mandatory": False},
                {"type": "ok_check",    "label": "Verify blower assembly completeness — all hardware installed"},
                {"type": "ok_check",    "label": "Connect test harness and instrumentation; verify zero calibration"},
                {"type": "text",        "label": "Serial Number (scan barcode)", "hint": "Scan or enter manually"},
                {"type": "radio",       "label": "FBL Model Number",
                 "options": ["FBL-400", "FBL-500", "FBL-600", "Phoenix FBL-500"]},
            ]},
            {"title": "Automated Performance Data", "type": "auto", "steps": [
                {"type": "instruction", "label": "Performance data captured automatically at 240 Hz steady-state.", "mandatory": False},
                {"type": "auto_number", "label": "Suction Pressure at 60 Hz",
                 "tol": {"lower": -50.0, "upper": -40.0, "unit": "kPa"}, "critical": True},
                {"type": "auto_number", "label": "Discharge Pressure at 60 Hz",
                 "tol": {"lower": 50.0, "upper": 60.0, "unit": "kPa"}, "critical": True},
                {"type": "auto_number", "label": "Current Draw at 60 Hz",
                 "tol": {"nominal": 4.2, "lower": 3.8, "upper": 4.6, "unit": "A"}, "critical": True},
                {"type": "auto_number", "label": "Noise Level",
                 "tol": {"nominal": 72.0, "lower": 65.0, "upper": 78.0, "unit": "dBA"}, "mandatory": False},
            ]},
            {"title": "Final Acceptance", "type": "manual", "steps": [
                {"type": "pass_fail", "label": "Visual inspection — no visible leaks, damage, or loose hardware", "critical": True},
                {"type": "pass_fail", "label": "Vibration spot-check at 60 Hz — no abnormal noise or vibration", "critical": True},
                {"type": "text",      "label": "Inspector name and sign-off"},
            ]},
        ]
    )


def _seed_p_series_procedure():
    _seed_procedure(
        "P-Series Pressure & Leak Test", "QA-WI-162", "1.4", "p_series",
        "P100 / P300 / P500 series pressure vessel and leak acceptance test",
        [
            {"title": "Safety Pre-Check", "type": "manual", "steps": [
                {"type": "ok_check", "label": "PPE verified — safety glasses and gloves worn"},
                {"type": "ok_check", "label": "Test area clear of non-essential personnel"},
                {"type": "ok_check", "label": "Pressure relief valve installed and verified functional"},
                {"type": "radio",    "label": "Model Series",
                 "options": ["P100-ECO", "P300-HPC", "P500-LPX"]},
                {"type": "text",     "label": "Unit Serial Number"},
            ]},
            {"title": "Pressure Test Data", "type": "auto", "steps": [
                {"type": "instruction", "label": "Test pressure applied and held; data captured automatically.", "mandatory": False},
                {"type": "auto_number", "label": "Applied Test Pressure",
                 "tol": {"nominal": 75.0, "lower": 73.0, "upper": 77.0, "unit": "PSI"}, "critical": True},
                {"type": "auto_number", "label": "Hold Duration",
                 "tol": {"nominal": 300.0, "lower": 295.0, "upper": 305.0, "unit": "s"}, "critical": True},
                {"type": "auto_number", "label": "Pressure Drop over Hold Period",
                 "tol": {"lower": 0.0, "upper": 1.5, "unit": "PSI"}, "critical": True},
                {"type": "auto_number", "label": "Ambient Temperature",
                 "tol": {"nominal": 72.0, "lower": 60.0, "upper": 90.0, "unit": "°F"}, "mandatory": False},
            ]},
            {"title": "Leak Verification", "type": "manual", "steps": [
                {"type": "pass_fail", "label": "Visual bubble-soap leak check — no bubbles observed", "critical": True},
                {"type": "number",   "label": "Final Stabilized Pressure Reading",
                 "tol": {"nominal": 75.0, "lower": 73.5, "upper": 76.5, "unit": "PSI"}},
                {"type": "text",     "label": "Inspector signature and date"},
            ]},
        ]
    )


def _seed_flow_procedure():
    _seed_procedure(
        "Flow Performance Test", "QA-WI-170", "3.0", "flow_perf",
        "F-Series blower flow performance and efficiency acceptance test",
        [
            {"title": "Setup & Configuration", "type": "instruction", "steps": [
                {"type": "instruction", "label": "Configure flow bench per setup drawing AT-FB-001.", "mandatory": False},
                {"type": "ok_check",    "label": "Install test unit and confirm all ports sealed per procedure"},
                {"type": "ok_check",    "label": "Zero all flow and pressure instrumentation"},
                {"type": "radio",       "label": "F-Series Model",
                 "options": ["F200-STD", "F400-PRO", "F400-HE"]},
                {"type": "text",        "label": "Unit Serial Number"},
            ]},
            {"title": "Automated Flow Measurements", "type": "auto", "steps": [
                {"type": "instruction", "label": "Flow data captured at steady-state. Allow 60 s warm-up before recording.", "mandatory": False},
                {"type": "auto_number", "label": "Flow Rate at 50 Hz",
                 "tol": {"nominal": 45.0, "lower": 42.0, "upper": 48.0, "unit": "SCFM"}, "critical": True},
                {"type": "auto_number", "label": "Flow Rate at 60 Hz",
                 "tol": {"nominal": 55.0, "lower": 52.0, "upper": 58.0, "unit": "SCFM"}, "critical": True},
                {"type": "auto_number", "label": "Differential Pressure",
                 "tol": {"nominal": 8.5, "lower": 7.5, "upper": 9.5, "unit": "in. H\u2082O"}, "critical": True},
                {"type": "auto_number", "label": "Power Consumption",
                 "tol": {"nominal": 280.0, "lower": 255.0, "upper": 305.0, "unit": "W"}, "critical": True},
                {"type": "auto_number", "label": "Overall Efficiency",
                 "tol": {"nominal": 68.0, "lower": 62.0, "upper": 74.0, "unit": "%"}, "mandatory": False},
            ]},
            {"title": "Acceptance Review", "type": "manual", "steps": [
                {"type": "pass_fail", "label": "All measured values within spec sheet tolerance", "critical": True},
                {"type": "text",     "label": "Record any deviations or observations"},
                {"type": "ok_check", "label": "Final approval — unit cleared for shipment"},
            ]},
        ]
    )


def _seed_demo_test_runs():
    """Seed ~50 test runs over the past 7 days across all 4 procedures."""
    _rnd.seed(77)

    # Ensure all 4 procedures exist
    ok, procs = run_query(
        "SELECT id, name, product_type FROM lab.test_procedures WHERE is_active=TRUE ORDER BY id"
    )
    if not ok:
        return
    if len(procs) < 2:
        _seed_fbl_procedure()
        _seed_p_series_procedure()
        _seed_flow_procedure()
        ok, procs = run_query(
            "SELECT id, name, product_type FROM lab.test_procedures WHERE is_active=TRUE ORDER BY id"
        )
        if not ok or not procs:
            return

    technicians = ["Marcus Webb", "Priya Nair", "Carlos Fuentes", "Dana Holloway", "James Okafor"]
    locations   = ["Test Bay A", "Test Bay B", "Test Bay C"]
    sn_prefixes = {"rook2": "RK", "fbl": "FB", "p_series": "PR", "flow_perf": "FL"}
    models      = {"rook2": "Rook2-122927", "fbl": "FBL-500", "p_series": "P300-HPC", "flow_perf": "F200-STD"}

    # Failure rates vary by procedure to make dashboard interesting
    fail_rates  = {"rook2": 0.12, "fbl": 0.22, "p_series": 0.18, "flow_perf": 0.15}

    today = date.today()
    for days_ago in range(7, 0, -1):
        run_date  = today - timedelta(days=days_ago)
        daily_cnt = _rnd.randint(5, 9)
        for _ in range(daily_cnt):
            proc    = _rnd.choice(procs)
            pt      = proc["product_type"] or "rook2"
            pfx     = sn_prefixes.get(pt, "AT")
            model   = models.get(pt, "AT-100")
            sn      = f"{pfx}-{_rnd.randint(1000, 9999)}"
            tech    = _rnd.choice(technicians)
            loc     = _rnd.choice(locations)
            is_fail = _rnd.random() < fail_rates.get(pt, 0.15)
            status  = "failed" if is_fail else "completed"
            ok2, run_row = run_write(
                """INSERT INTO lab.test_runs
                   (procedure_id, serial_number, model_number, test_location,
                    technician_name, status, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (proc["id"], sn, model, loc, tech, status,
                 run_date.isoformat(), run_date.isoformat()),
            )
            if ok2 and run_row:
                _generate_run_responses(run_row["id"], proc["id"], status)


# Run schema init in background so startup isn't blocked
threading.Thread(target=_init_schema, daemon=True).start()


@app.route("/")
def index():
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.route("/<path:path>")
def spa_files(path):
    full = STATIC_DIR / path
    if full.exists():
        return send_from_directory(str(STATIC_DIR), path)
    return send_from_directory(str(STATIC_DIR), "index.html")


# ── Helpers ────────────────────────────────────────────────────────────────────
def _json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    try:
        from decimal import Decimal
        if isinstance(obj, Decimal):
            return float(obj)
    except ImportError:
        pass
    raise TypeError(f"Type {type(obj)} not serializable")


def _ok(data, status=200):
    return app.response_class(
        json.dumps(data, default=_json_serial),
        status=status,
        mimetype="application/json",
    )


def _err(msg, status=400):
    return jsonify({"error": msg}), status


# ── Status ─────────────────────────────────────────────────────────────────────
@app.get("/api/status")
def api_status():
    db_ok, db_error = True, None
    ok, rows = run_query("SELECT 1")
    if not ok:
        db_ok = False
        db_error = rows[0].get("error") if rows else "unknown"
    return _ok({
        "db_ok": db_ok,
        "db_error": db_error,
        "db_url_set": bool(config.DATABASE_URL),
        "databricks_configured": bool(config.DATABRICKS_HOST and config.DATABRICKS_TOKEN),
        "machines": config.get_machines(),
    })


# ── Machines ───────────────────────────────────────────────────────────────────
@app.get("/api/machines")
def list_machines():
    return _ok(config.get_machines())


# ── Bronze layer readings ──────────────────────────────────────────────────────
@app.get("/api/readings")
def list_readings():
    machine_id = request.args.get("machine_id")
    if not machine_id:
        # Return the most recent `limit` readings across all machines
        limit = int(request.args.get("limit", 60))
        all_readings = []
        for m in config.get_machines():
            r = dbc.get_readings(m["id"], limit=limit)
            all_readings.extend(r)
        all_readings.sort(key=lambda x: x.get("recorded_at", ""), reverse=True)
        return _ok(all_readings[:limit])

    limit  = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    readings = dbc.get_readings(machine_id, limit=limit, offset=offset)
    return _ok(readings)


@app.get("/api/readings/<machine_id>/<reading_id>")
def get_reading(machine_id, reading_id):
    reading = dbc.get_reading(machine_id, reading_id)
    if not reading:
        return _err("Not found", 404)

    # Attach enhancement if it exists
    _, enh = run_query(
        "SELECT * FROM lab.reading_enhancements WHERE bronze_reading_id=%s ORDER BY created_at DESC LIMIT 1",
        (reading_id,)
    )
    reading["enhancement"] = enh[0] if enh else None
    return _ok(reading)


# ── Enhancements (manual overlay on bronze readings) ──────────────────────────
@app.get("/api/enhancements")
def list_enhancements():
    clauses, params = [], []
    if mid := request.args.get("machine_id"):
        clauses.append("machine_id=%s"); params.append(mid)
    if tid := request.args.get("technician_id"):
        clauses.append("technician_id=%s"); params.append(tid)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    ok, rows = run_query(
        f"""SELECT e.*, t.name AS technician_name
            FROM lab.reading_enhancements e
            LEFT JOIN lab.technicians t ON t.id=e.technician_id
            {where}
            ORDER BY e.created_at DESC LIMIT 100""",
        params
    )
    return _ok(rows) if ok else _err(rows[0].get("error", "DB error") if rows else "DB error")


@app.get("/api/enhancements/<reading_id>")
def get_enhancement(reading_id):
    ok, rows = run_query(
        """SELECT e.*, t.name AS technician_name
           FROM lab.reading_enhancements e
           LEFT JOIN lab.technicians t ON t.id=e.technician_id
           WHERE e.bronze_reading_id=%s
           ORDER BY e.created_at DESC LIMIT 1""",
        (reading_id,)
    )
    if not ok or not rows:
        return _err("Not found", 404)
    return _ok(rows[0])


@app.post("/api/enhancements")
def create_enhancement():
    b = request.json
    ok, row = run_write(
        """INSERT INTO lab.reading_enhancements
           (bronze_reading_id, machine_id, technician_id,
            visual_inspection, anomalies_noted, corrective_actions,
            override_values, manual_measurements, confidence_in_data, notes)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (b["bronze_reading_id"], b.get("machine_id"), b.get("technician_id"),
         b.get("visual_inspection"), b.get("anomalies_noted"), b.get("corrective_actions"),
         json.dumps(b.get("override_values", {})),
         json.dumps(b.get("manual_measurements", [])),
         b.get("confidence_in_data", 3),
         b.get("notes"))
    )
    if not ok:
        return _err(row.get("error", ""))
    return _ok(row, 201)


@app.patch("/api/enhancements/<int:eid>")
def update_enhancement(eid):
    b = request.json
    allowed = {"visual_inspection", "anomalies_noted", "corrective_actions",
               "override_values", "manual_measurements", "confidence_in_data", "notes"}
    sets, params = [], []
    for k, v in b.items():
        if k in allowed:
            val = json.dumps(v) if isinstance(v, (dict, list)) else v
            sets.append(f"{k}=%s"); params.append(val)
    if not sets:
        return _err("No valid fields")
    sets.append("updated_at=NOW()")
    params.append(eid)
    ok, row = run_write(
        f"UPDATE lab.reading_enhancements SET {', '.join(sets)} WHERE id=%s RETURNING *",
        params
    )
    return _ok(row) if ok else _err(row.get("error", ""))


# ── Technicians ────────────────────────────────────────────────────────────────
@app.get("/api/technicians")
def list_technicians():
    ok, rows = run_query(
        "SELECT * FROM lab.technicians WHERE is_active=TRUE ORDER BY name"
    )
    return _ok(rows) if ok else _err(rows[0].get("error", "DB error") if rows else "DB error")


@app.post("/api/technicians")
def create_technician():
    b = request.json
    ok, row = run_write(
        """INSERT INTO lab.technicians (name, badge_id, specialty, email)
           VALUES (%s,%s,%s,%s) RETURNING *""",
        (b["name"], b.get("badge_id"), b.get("specialty"), b.get("email"))
    )
    return _ok(row, 201) if ok else _err(row.get("error", ""))


# ── Test schedule (leaderboard) ────────────────────────────────────────────────
@app.get("/api/schedule")
def list_schedule():
    clauses, params = [], []
    if st := request.args.get("status"):
        clauses.append("s.status=%s"); params.append(st)
    else:
        clauses.append("s.status IN ('scheduled','in_progress')")
    if tid := request.args.get("technician_id"):
        clauses.append("s.technician_id=%s"); params.append(tid)
    if mid := request.args.get("machine_id"):
        clauses.append("s.machine_id=%s"); params.append(mid)
    where = "WHERE " + " AND ".join(clauses)
    ok, rows = run_query(
        f"""SELECT s.*,
               t.name AS technician_name,
               t.specialty AS technician_specialty
            FROM lab.test_schedule s
            LEFT JOIN lab.technicians t ON t.id=s.technician_id
            {where}
            ORDER BY
                CASE s.priority
                    WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                    WHEN 'normal'   THEN 3 ELSE 4 END,
                s.scheduled_at ASC
            LIMIT 200""",
        params
    )
    return _ok(rows) if ok else _err(rows[0].get("error", "DB error") if rows else "DB error")


@app.post("/api/schedule")
def create_schedule():
    b = request.json
    ok, row = run_write(
        """INSERT INTO lab.test_schedule
           (title, sample_id, reading_id, machine_id, test_type,
            scheduled_at, estimated_duration_min, priority,
            technician_id, notes)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (b["title"], b.get("sample_id"), b.get("reading_id"),
         b.get("machine_id"), b.get("test_type"),
         b.get("scheduled_at"), b.get("estimated_duration_min", 60),
         b.get("priority", "normal"), b.get("technician_id"), b.get("notes"))
    )
    return _ok(row, 201) if ok else _err(row.get("error", ""))


@app.patch("/api/schedule/<int:sid>")
def update_schedule(sid):
    b = request.json
    allowed = {"title", "status", "priority", "technician_id", "scheduled_at",
               "estimated_duration_min", "notes", "sample_id", "machine_id"}
    sets, params = [], []
    for k, v in b.items():
        if k in allowed:
            sets.append(f"{k}=%s"); params.append(v)
    if not sets:
        return _err("No valid fields")
    if b.get("status") == "in_progress":
        sets.append("started_at=COALESCE(started_at, NOW())")
    if b.get("status") == "completed":
        sets.append("completed_at=NOW()")
    sets.append("updated_at=NOW()")
    params.append(sid)
    ok, row = run_write(
        f"UPDATE lab.test_schedule SET {', '.join(sets)} WHERE id=%s RETURNING *",
        params
    )
    return _ok(row) if ok else _err(row.get("error", ""))


@app.delete("/api/schedule/<int:sid>")
def delete_schedule(sid):
    ok, row = run_write(
        "UPDATE lab.test_schedule SET status='cancelled', updated_at=NOW() WHERE id=%s RETURNING id",
        (sid,)
    )
    return _ok(row) if ok else _err(row.get("error", ""))


# ── Leaderboard summary ────────────────────────────────────────────────────────
@app.get("/api/leaderboard/summary")
def leaderboard_summary():
    """Aggregate KPIs for the leaderboard header."""
    ok, rows = run_query("""
        SELECT
            COUNT(*) FILTER (WHERE status='scheduled')   AS scheduled_count,
            COUNT(*) FILTER (WHERE status='in_progress') AS in_progress_count,
            COUNT(*) FILTER (WHERE status='completed'
                AND completed_at >= NOW() - INTERVAL '24 hours') AS completed_today,
            COUNT(*) FILTER (WHERE priority='critical'
                AND status IN ('scheduled','in_progress')) AS critical_pending
        FROM lab.test_schedule
    """)
    _, tech_load = run_query("""
        SELECT t.id, t.name, t.specialty,
            COUNT(s.id) FILTER (WHERE s.status IN ('scheduled','in_progress')) AS active_tests,
            COUNT(s.id) FILTER (WHERE s.status='completed'
                AND s.completed_at >= NOW() - INTERVAL '24 hours') AS completed_today
        FROM lab.technicians t
        LEFT JOIN lab.test_schedule s ON s.technician_id=t.id
        WHERE t.is_active=TRUE
        GROUP BY t.id, t.name, t.specialty
        ORDER BY active_tests DESC
    """)
    result = rows[0] if rows else {}
    result["technician_load"] = tech_load
    return _ok(result)


# ── Technician workload ────────────────────────────────────────────────────────
@app.get("/api/technicians/<int:tid>/schedule")
def technician_schedule(tid):
    ok, rows = run_query(
        """SELECT s.*
           FROM lab.test_schedule s
           WHERE s.technician_id=%s AND s.status IN ('scheduled','in_progress')
           ORDER BY
               CASE s.priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 ELSE 4 END,
               s.scheduled_at ASC""",
        (tid,)
    )
    return _ok(rows) if ok else _err(rows[0]["error"])


# ── Inspection master data ─────────────────────────────────────────────────────
@app.get("/api/inspection/master")
def get_inspection_master():
    ok, rows = run_query("SELECT key, items FROM lab.insp_master")
    if not ok:
        return _err("DB error")
    return _ok({r["key"]: r["items"] for r in rows})


@app.put("/api/inspection/master")
def update_inspection_master():
    b = request.json or {}
    allowed = {"charDesignators", "tools", "sampleRates", "machinists", "adminPin"}
    for key, items in b.items():
        if key not in allowed:
            continue
        run_write(
            "INSERT INTO lab.insp_master (key, items) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET items = EXCLUDED.items",
            (key, json.dumps(items)),
            returning=False,
        )
    return _ok({"updated": True})


# ── Inspection records ─────────────────────────────────────────────────────────
@app.get("/api/inspection/records")
def list_inspection_records():
    limit     = min(int(request.args.get("limit", 200)), 500)
    product   = request.args.get("product")
    machinist = request.args.get("machinist")
    date_str  = request.args.get("date")
    only_fail = request.args.get("status") == "failed"

    clauses, params = [], []
    if product:   clauses.append("r.product=%s");          params.append(product)
    if machinist: clauses.append("r.machinist=%s");        params.append(machinist)
    if date_str:  clauses.append("r.inspection_date=%s"); params.append(date_str)
    where  = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    having = f"HAVING {_FAIL_EXPR}" if only_fail else ""

    ok, rows = run_query(
        f"""SELECT r.id, r.product, r.wo_number, r.inspection_date,
                   r.part_number, r.serial_number, r.operation,
                   r.equipment, r.machinist, r.status, r.created_at,
                   {_FAIL_EXPR} AS has_fail,
                   COUNT(ir.id) AS row_count
            FROM lab.inspection_records r
            LEFT JOIN lab.inspection_rows ir ON ir.record_id = r.id
            {where}
            GROUP BY r.id, r.product, r.wo_number, r.inspection_date,
                     r.part_number, r.serial_number, r.operation,
                     r.equipment, r.machinist, r.status, r.created_at
            {having}
            ORDER BY r.inspection_date DESC, r.created_at DESC
            LIMIT %s""",
        params + [limit]
    )
    return _ok(rows) if ok else _err("DB error")


@app.get("/api/inspection/records/<int:rid>")
def get_inspection_record(rid):
    ok, rows = run_query("SELECT * FROM lab.inspection_records WHERE id=%s", (rid,))
    if not ok or not rows:
        return _err("Not found", 404)
    record = rows[0]
    _, irows = run_query(
        "SELECT * FROM lab.inspection_rows WHERE record_id=%s ORDER BY row_number",
        (rid,)
    )
    record["rows"] = irows
    return _ok(record)


@app.post("/api/inspection/records")
def create_inspection_record():
    b = request.json or {}
    hdr = b.get("header", {})
    tc  = b.get("tool_change", {})
    form_rows = b.get("rows", [])

    ok, rec = run_write(
        """INSERT INTO lab.inspection_records
           (product, wo_number, inspection_date, part_number,
            serial_number, operation, equipment, machinist, tool_change)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (hdr.get("product"), hdr.get("woNumber"),
         hdr.get("date") or None,
         hdr.get("partNumber"), hdr.get("serialNumber"),
         hdr.get("operation"), hdr.get("equipment"),
         hdr.get("machinist"), json.dumps(tc))
    )
    if not ok:
        return _err(rec.get("error", "DB error"))

    rid = rec["id"]
    for i, row in enumerate(form_rows):
        insp = row.get("insp", [])
        while len(insp) < 9:
            insp.append("")
        run_write(
            """INSERT INTO lab.inspection_rows
               (record_id, row_number, char_designator, requirement, tool, sample_rate,
                piece_1st, piece_5th, piece_10th, piece_15th, piece_20th,
                piece_25th, piece_30th, piece_35th, piece_iqa, sn_values)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (rid, i + 1,
             row.get("charDesig"), row.get("requirement"),
             row.get("tool"), row.get("sampleRate"),
             insp[0], insp[1], insp[2], insp[3], insp[4],
             insp[5], insp[6], insp[7], insp[8],
             json.dumps(row.get("sn", []))),
            returning=False,
        )

    return _ok(rec, 201)


@app.patch("/api/inspection/records/<int:rid>")
def update_inspection_record_status(rid):
    b = request.json or {}
    allowed = {"status", "product", "wo_number", "machinist"}
    sets, params = [], []
    for k, v in b.items():
        if k in allowed:
            sets.append(f"{k}=%s"); params.append(v)
    if not sets:
        return _err("No valid fields")
    sets.append("updated_at=NOW()")
    params.append(rid)
    ok, row = run_write(
        f"UPDATE lab.inspection_records SET {', '.join(sets)} WHERE id=%s RETURNING *",
        params
    )
    return _ok(row) if ok else _err(row.get("error", ""))


# ── WO Catalog ─────────────────────────────────────────────────────────────────
@app.get("/api/inspection/wo-catalog")
def list_wo_catalog():
    active_only = request.args.get("active", "1") != "0"
    clause = "WHERE is_active=TRUE" if active_only else ""
    ok, rows = run_query(f"SELECT * FROM lab.wo_catalog {clause} ORDER BY wo_number")
    return _ok(rows) if ok else _err("DB error")


@app.post("/api/inspection/wo-catalog")
def create_wo_entry():
    b = request.json or {}
    ok, row = run_write(
        "INSERT INTO lab.wo_catalog (wo_number, product, part_number, description) "
        "VALUES (%s,%s,%s,%s) RETURNING *",
        (b["wo_number"], b["product"], b.get("part_number"), b.get("description")),
    )
    return _ok(row, 201) if ok else _err(row.get("error", "DB error"))


@app.patch("/api/inspection/wo-catalog/<int:wid>")
def update_wo_entry(wid):
    b = request.json or {}
    allowed = {"wo_number", "product", "part_number", "description", "is_active"}
    sets, params = [], []
    for k, v in b.items():
        if k in allowed:
            sets.append(f"{k}=%s"); params.append(v)
    if not sets:
        return _err("No valid fields")
    sets.append("updated_at=NOW()")
    params.append(wid)
    ok, row = run_write(
        f"UPDATE lab.wo_catalog SET {', '.join(sets)} WHERE id=%s RETURNING *", params
    )
    return _ok(row) if ok else _err(row.get("error", ""))


# ── Inspection Templates ────────────────────────────────────────────────────────
@app.get("/api/inspection/templates")
def list_templates():
    ok, rows = run_query(
        """SELECT t.id, t.name, t.product, t.part_number, t.description,
                  t.operation, t.is_active,
                  COUNT(r.id) AS row_count
           FROM lab.insp_templates t
           LEFT JOIN lab.insp_template_rows r ON r.template_id = t.id
           WHERE t.is_active = TRUE
           GROUP BY t.id
           ORDER BY t.name"""
    )
    return _ok(rows) if ok else _err("DB error")


@app.get("/api/inspection/templates/<int:tid>")
def get_template(tid):
    ok, rows = run_query("SELECT * FROM lab.insp_templates WHERE id=%s", (tid,))
    if not ok or not rows:
        return _err("Not found", 404)
    tmpl = rows[0]
    _, trows = run_query(
        "SELECT * FROM lab.insp_template_rows WHERE template_id=%s ORDER BY row_number",
        (tid,),
    )
    tmpl["rows"] = trows
    return _ok(tmpl)


@app.post("/api/inspection/templates")
def create_template():
    b = request.json or {}
    ok, tmpl = run_write(
        """INSERT INTO lab.insp_templates (name, product, part_number, description, operation)
           VALUES (%s,%s,%s,%s,%s) RETURNING *""",
        (b["name"], b.get("product"), b.get("part_number"),
         b.get("description"), b.get("operation")),
    )
    if not ok:
        return _err(tmpl.get("error", "DB error"))
    _upsert_template_rows(tmpl["id"], b.get("rows", []))
    return _ok(tmpl, 201)


@app.put("/api/inspection/templates/<int:tid>")
def update_template(tid):
    b = request.json or {}
    allowed_fields = {"name", "product", "part_number", "description", "operation"}
    sets, params = [], []
    for k, v in b.items():
        if k in allowed_fields:
            sets.append(f"{k}=%s"); params.append(v)
    if sets:
        sets.append("updated_at=NOW()")
        params.append(tid)
        run_write(
            f"UPDATE lab.insp_templates SET {', '.join(sets)} WHERE id=%s",
            params, returning=False,
        )
    if "rows" in b:
        _upsert_template_rows(tid, b["rows"])
    ok, rows = run_query("SELECT * FROM lab.insp_templates WHERE id=%s", (tid,))
    return _ok(rows[0]) if ok and rows else _err("Not found", 404)


@app.delete("/api/inspection/templates/<int:tid>")
def delete_template(tid):
    ok, row = run_write(
        "UPDATE lab.insp_templates SET is_active=FALSE, updated_at=NOW() WHERE id=%s RETURNING id",
        (tid,),
    )
    return _ok(row) if ok else _err(row.get("error", ""))


def _upsert_template_rows(template_id: int, rows: list):
    run_write(
        "DELETE FROM lab.insp_template_rows WHERE template_id=%s",
        (template_id,), returning=False,
    )
    for row in rows:
        run_write(
            """INSERT INTO lab.insp_template_rows
               (template_id, row_number, char_designator, requirement, tool, sample_rate)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (template_id, row.get("row_number", 1),
             row.get("char_designator"), row.get("requirement"),
             row.get("tool"), row.get("sample_rate")),
            returning=False,
        )


# ── Inspection Export ──────────────────────────────────────────────────────────
@app.get("/api/inspection/export")
def export_inspections():
    import csv, io
    ok, rows = run_query("""
        SELECT
            DENSE_RANK() OVER (ORDER BY r.id)         AS "Record Group",
            COALESCE(r.product, '')                    AS "Product",
            COALESCE(r.wo_number, '')                  AS "W.O. Number",
            COALESCE(r.inspection_date::text, '')      AS "Date",
            COALESCE(r.part_number, '')                AS "Part Number",
            COALESCE(r.serial_number, '')              AS "Serial Number",
            COALESCE(r.operation, '')                  AS "Operation",
            COALESCE(r.equipment, '')                  AS "Equipment",
            COALESCE(r.machinist, '')                  AS "Machinist",
            COALESCE(ir.char_designator, '')           AS "Char Designator",
            COALESCE(ir.requirement, '')               AS "Requirement",
            COALESCE(ir.tool, '')                      AS "Tool",
            COALESCE(ir.sample_rate, '')               AS "Sample Rate",
            COALESCE(ir.piece_1st, '')                 AS "1st Piece",
            COALESCE(ir.piece_5th, '')                 AS "5th Piece",
            COALESCE(ir.piece_10th, '')                AS "10th Piece",
            COALESCE(ir.piece_15th, '')                AS "15th Piece",
            COALESCE(ir.piece_20th, '')                AS "20th Piece",
            COALESCE(ir.piece_25th, '')                AS "25th Piece",
            COALESCE(ir.piece_30th, '')                AS "30th Piece",
            COALESCE(ir.piece_35th, '')                AS "35th Piece",
            COALESCE(ir.piece_iqa, '')                 AS "IQA"
        FROM lab.inspection_records r
        LEFT JOIN lab.inspection_rows ir ON ir.record_id = r.id
        ORDER BY r.id, ir.row_number
    """)
    if not ok:
        return _err("DB error")

    fieldnames = [
        "Record Group", "Product", "W.O. Number", "Date", "Part Number",
        "Serial Number", "Operation", "Equipment", "Machinist",
        "Char Designator", "Requirement", "Tool", "Sample Rate",
        "1st Piece", "5th Piece", "10th Piece", "15th Piece", "20th Piece",
        "25th Piece", "30th Piece", "35th Piece", "IQA",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

    from flask import Response
    filename = f"inspections_{date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        status=200,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Inspection Import ───────────────────────────────────────────────────────────
@app.post("/api/inspection/import")
def import_inspections():
    records = request.json or []
    imported, errors = 0, []
    for i, rec in enumerate(records):
        ok, row = run_write(
            """INSERT INTO lab.inspection_records
               (product, wo_number, inspection_date, part_number, serial_number,
                operation, equipment, machinist, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'complete') RETURNING id""",
            (rec.get("product"), rec.get("wo_number"),
             rec.get("inspection_date") or None,
             rec.get("part_number"), rec.get("serial_number"),
             rec.get("operation"), rec.get("equipment"), rec.get("machinist")),
        )
        if not ok:
            errors.append({"record": i + 1, "error": row.get("error", "DB error")})
            continue
        rid = row["id"]
        for j, ir in enumerate(rec.get("rows", [])):
            run_write(
                """INSERT INTO lab.inspection_rows
                   (record_id, row_number, char_designator, requirement, tool,
                    sample_rate, piece_1st, piece_5th, piece_10th, piece_15th,
                    piece_20th, piece_25th, piece_30th, piece_35th, piece_iqa)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (rid, j + 1,
                 ir.get("char_designator"), ir.get("requirement"),
                 ir.get("tool"), ir.get("sample_rate"),
                 ir.get("piece_1st"), ir.get("piece_5th"), ir.get("piece_10th"),
                 ir.get("piece_15th"), ir.get("piece_20th"), ir.get("piece_25th"),
                 ir.get("piece_30th"), ir.get("piece_35th"), ir.get("piece_iqa")),
                returning=False,
            )
        imported += 1
    return _ok({"imported": imported, "errors": errors})


# ── Inspection Dashboard ────────────────────────────────────────────────────────
_FAIL_EXPR = """BOOL_OR(
        LOWER(COALESCE(ir.piece_1st, ''))  IN ('fail','f') OR
        LOWER(COALESCE(ir.piece_5th, ''))  IN ('fail','f') OR
        LOWER(COALESCE(ir.piece_10th,''))  IN ('fail','f') OR
        LOWER(COALESCE(ir.piece_15th,''))  IN ('fail','f') OR
        LOWER(COALESCE(ir.piece_20th,''))  IN ('fail','f') OR
        LOWER(COALESCE(ir.piece_25th,''))  IN ('fail','f') OR
        LOWER(COALESCE(ir.piece_30th,''))  IN ('fail','f') OR
        LOWER(COALESCE(ir.piece_35th,''))  IN ('fail','f') OR
        LOWER(COALESCE(ir.piece_iqa,  '')) IN ('fail','f')
    )"""

_BASE_CTE = f"""
    WITH pf AS (
        SELECT r.id, r.product, r.machinist, r.operation,
               r.inspection_date, r.status,
               COUNT(ir.id) AS row_count,
               {_FAIL_EXPR} AS has_fail
        FROM lab.inspection_records r
        LEFT JOIN lab.inspection_rows ir ON ir.record_id = r.id
        GROUP BY r.id, r.product, r.machinist, r.operation, r.inspection_date, r.status
    )
"""


@app.get("/api/inspection/dashboard")
def inspection_dashboard():
    _, totals = run_query(_BASE_CTE + """
        SELECT
            COUNT(*)                                                             AS total,
            SUM(CASE WHEN NOT COALESCE(has_fail,false) THEN 1 ELSE 0 END)       AS passed,
            SUM(CASE WHEN     COALESCE(has_fail,false) THEN 1 ELSE 0 END)       AS failed,
            ROUND(100.0 * SUM(CASE WHEN NOT COALESCE(has_fail,false) THEN 1 ELSE 0 END)
                  / NULLIF(COUNT(*), 0), 1)                                      AS pass_rate,
            ROUND(AVG(row_count), 1)                                             AS avg_rows,
            COUNT(DISTINCT product)                                              AS distinct_products
        FROM pf
    """)
    _, by_product = run_query(_BASE_CTE + """
        SELECT product,
            COUNT(*)                                                             AS total,
            SUM(CASE WHEN NOT COALESCE(has_fail,false) THEN 1 ELSE 0 END)       AS passed,
            SUM(CASE WHEN     COALESCE(has_fail,false) THEN 1 ELSE 0 END)       AS failed,
            ROUND(100.0 * SUM(CASE WHEN NOT COALESCE(has_fail,false) THEN 1 ELSE 0 END)
                  / NULLIF(COUNT(*), 0), 1)                                      AS pass_rate
        FROM pf WHERE product IS NOT NULL
        GROUP BY product ORDER BY total DESC LIMIT 10
    """)
    _, by_machinist = run_query(_BASE_CTE + """
        SELECT machinist,
            COUNT(*)                                                             AS total,
            SUM(CASE WHEN NOT COALESCE(has_fail,false) THEN 1 ELSE 0 END)       AS passed,
            SUM(CASE WHEN     COALESCE(has_fail,false) THEN 1 ELSE 0 END)       AS failed,
            ROUND(100.0 * SUM(CASE WHEN NOT COALESCE(has_fail,false) THEN 1 ELSE 0 END)
                  / NULLIF(COUNT(*), 0), 1)                                      AS pass_rate
        FROM pf WHERE machinist IS NOT NULL
        GROUP BY machinist ORDER BY total DESC
    """)
    _, by_operation = run_query(_BASE_CTE + """
        SELECT operation,
            COUNT(*) AS total,
            SUM(CASE WHEN COALESCE(has_fail,false) THEN 1 ELSE 0 END) AS failed
        FROM pf WHERE operation IS NOT NULL
        GROUP BY operation ORDER BY total DESC
    """)
    _, trend = run_query(f"""
        WITH insp_pf AS (
            SELECT r.inspection_date::date AS day,
                   {_FAIL_EXPR} AS has_fail
            FROM lab.inspection_records r
            LEFT JOIN lab.inspection_rows ir ON ir.record_id = r.id
            WHERE r.inspection_date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY r.id, r.inspection_date
        ),
        insp_daily AS (
            SELECT day,
                   SUM(CASE WHEN NOT COALESCE(has_fail,false) THEN 1 ELSE 0 END) AS i_passed,
                   SUM(CASE WHEN     COALESCE(has_fail,false) THEN 1 ELSE 0 END) AS i_failed
            FROM insp_pf GROUP BY day
        ),
        run_daily AS (
            SELECT DATE(created_at) AS day,
                   SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS r_passed,
                   SUM(CASE WHEN status='failed'    THEN 1 ELSE 0 END) AS r_failed
            FROM lab.test_runs
            WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
              AND status IN ('completed','failed')
            GROUP BY DATE(created_at)
        )
        SELECT COALESCE(i.day, r.day)::text AS day,
               COALESCE(i.i_passed, 0) + COALESCE(r.r_passed, 0) AS passed,
               COALESCE(i.i_failed, 0) + COALESCE(r.r_failed, 0) AS failed,
               COALESCE(i.i_passed, 0) + COALESCE(r.r_passed, 0) +
               COALESCE(i.i_failed, 0) + COALESCE(r.r_failed, 0) AS total
        FROM insp_daily i
        FULL OUTER JOIN run_daily r ON i.day = r.day
        ORDER BY day
    """)
    return _ok({
        "totals":       totals[0]    if totals    else {},
        "by_product":   by_product,
        "by_machinist": by_machinist,
        "by_operation": by_operation,
        "trend":        trend,
    })


# ── Test Procedures ────────────────────────────────────────────────────────────
@app.get("/api/procedures")
def list_procedures():
    ok, rows = run_query(
        "SELECT * FROM lab.test_procedures WHERE is_active=TRUE ORDER BY name"
    )
    return _ok(rows) if ok else _err("DB error")


@app.get("/api/procedures/<int:pid>")
def get_procedure(pid):
    ok, rows = run_query("SELECT * FROM lab.test_procedures WHERE id=%s", (pid,))
    if not ok or not rows:
        return _err("Not found", 404)
    proc = rows[0]
    _, sections = run_query(
        "SELECT * FROM lab.test_proc_sections WHERE procedure_id=%s ORDER BY order_index",
        (pid,)
    )
    for sec in (sections or []):
        _, steps = run_query(
            "SELECT * FROM lab.test_proc_steps WHERE section_id=%s ORDER BY order_index",
            (sec["id"],)
        )
        for step in (steps or []):
            _, imgs = run_query(
                "SELECT id, filename, mime_type, data_b64 FROM lab.test_proc_step_images "
                "WHERE step_id=%s ORDER BY order_index, created_at",
                (step["id"],)
            )
            step["images"] = imgs or []
        sec["steps"] = steps or []
    proc["sections"] = sections or []
    return _ok(proc)


@app.post("/api/procedures")
def create_procedure():
    b = request.json or {}
    ok, proc = run_write(
        """INSERT INTO lab.test_procedures (name, doc_id, version, product_type, description)
           VALUES (%s,%s,%s,%s,%s) RETURNING *""",
        (b["name"], b.get("doc_id"), b.get("version"),
         b.get("product_type"), b.get("description")),
    )
    if not ok:
        return _err(proc.get("error", "DB error"))
    for i, sec in enumerate(b.get("sections", [])):
        _upsert_proc_section(proc["id"], sec, i + 1)
    return _ok(proc, 201)


@app.put("/api/procedures/<int:pid>")
def update_procedure(pid):
    b = request.json or {}
    allowed = {"name", "doc_id", "version", "product_type", "description"}
    sets, params = [], []
    for k, v in b.items():
        if k in allowed:
            sets.append(f"{k}=%s"); params.append(v)
    if sets:
        sets.append("updated_at=NOW()")
        params.append(pid)
        run_write(f"UPDATE lab.test_procedures SET {', '.join(sets)} WHERE id=%s",
                  params, returning=False)
    if "sections" in b:
        _merge_proc_sections(pid, b["sections"])
    ok, rows = run_query("SELECT * FROM lab.test_procedures WHERE id=%s", (pid,))
    return _ok(rows[0]) if ok and rows else _err("Not found", 404)


@app.delete("/api/procedures/<int:pid>")
def delete_procedure(pid):
    ok, row = run_write(
        "UPDATE lab.test_procedures SET is_active=FALSE, updated_at=NOW() WHERE id=%s RETURNING id",
        (pid,)
    )
    return _ok(row) if ok else _err(row.get("error", ""))


def _merge_proc_steps(section_id: int, incoming_steps: list):
    """Upsert steps preserving IDs so step images survive a procedure re-save."""
    _, existing = run_query("SELECT id FROM lab.test_proc_steps WHERE section_id=%s", (section_id,))
    existing_ids = {r["id"] for r in (existing or [])}
    seen_ids: set = set()
    for j, step in enumerate(incoming_steps):
        sid   = step.get("id")
        opts  = json.dumps(step.get("options_json", []))
        tols  = json.dumps(step.get("tolerances_json", {}))
        cond  = json.dumps(step["condition_json"]) if step.get("condition_json") else None
        vals  = (j + 1, step["step_type"], step.get("label", ""),
                 opts, tols, step.get("is_mandatory", True),
                 step.get("is_critical", False), cond, step.get("hint_text"))
        if sid and sid in existing_ids:
            run_write("""UPDATE lab.test_proc_steps
                        SET order_index=%s, step_type=%s, label=%s, options_json=%s,
                            tolerances_json=%s, is_mandatory=%s, is_critical=%s,
                            condition_json=%s, hint_text=%s
                        WHERE id=%s""",
                     (*vals, sid), returning=False)
            seen_ids.add(sid)
        else:
            ok, row = run_write("""INSERT INTO lab.test_proc_steps
               (section_id, order_index, step_type, label, options_json, tolerances_json,
                is_mandatory, is_critical, condition_json, hint_text)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
               (section_id, *vals))
            if ok and row:
                seen_ids.add(row["id"])
    for old_id in existing_ids - seen_ids:
        run_write("DELETE FROM lab.test_proc_steps WHERE id=%s", (old_id,), returning=False)


def _merge_proc_sections(procedure_id: int, incoming_sections: list):
    """Upsert sections + steps preserving IDs."""
    _, existing = run_query("SELECT id FROM lab.test_proc_sections WHERE procedure_id=%s", (procedure_id,))
    existing_ids = {r["id"] for r in (existing or [])}
    seen_ids: set = set()
    for i, sec in enumerate(incoming_sections):
        sid = sec.get("id")
        if sid and sid in existing_ids:
            run_write(
                "UPDATE lab.test_proc_sections SET title=%s, section_type=%s, order_index=%s WHERE id=%s",
                (sec["title"], sec.get("section_type", "manual"), i + 1, sid),
                returning=False,
            )
            seen_ids.add(sid)
        else:
            ok, row = run_write(
                """INSERT INTO lab.test_proc_sections
                   (procedure_id, order_index, title, section_type)
                   VALUES (%s,%s,%s,%s) RETURNING id""",
                (procedure_id, i + 1, sec["title"], sec.get("section_type", "manual")),
            )
            sid = row["id"] if ok and row else None
            if sid:
                seen_ids.add(sid)
        if sid:
            _merge_proc_steps(sid, sec.get("steps", []))
    for old_id in existing_ids - seen_ids:
        run_write("DELETE FROM lab.test_proc_sections WHERE id=%s", (old_id,), returning=False)


def _upsert_proc_section(procedure_id: int, sec: dict, order_index: int):
    ok2, sec_row = run_write(
        """INSERT INTO lab.test_proc_sections (procedure_id, order_index, title, section_type)
           VALUES (%s,%s,%s,%s) RETURNING id""",
        (procedure_id, order_index, sec["title"], sec.get("section_type", "manual")),
    )
    if not ok2:
        return
    sid = sec_row["id"]
    for j, step in enumerate(sec.get("steps", [])):
        run_write(
            """INSERT INTO lab.test_proc_steps
               (section_id, order_index, step_type, label, options_json, tolerances_json,
                is_mandatory, is_critical, condition_json, hint_text)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (sid, j + 1, step["step_type"], step["label"],
             json.dumps(step.get("options_json", [])),
             json.dumps(step.get("tolerances_json", {})),
             step.get("is_mandatory", True), step.get("is_critical", False),
             json.dumps(step["condition_json"]) if step.get("condition_json") else None,
             step.get("hint_text")),
            returning=False,
        )


# ── Test Runs ──────────────────────────────────────────────────────────────────
@app.get("/api/test-runs")
def list_test_runs():
    clauses, params = [], []
    if pid := request.args.get("procedure_id"):
        clauses.append("r.procedure_id=%s"); params.append(pid)
    if st := request.args.get("status"):
        clauses.append("r.status=%s"); params.append(st)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    ok, rows = run_query(
        f"""SELECT r.*, p.name AS procedure_name, p.doc_id
            FROM lab.test_runs r
            JOIN lab.test_procedures p ON p.id=r.procedure_id
            {where}
            ORDER BY r.created_at DESC LIMIT 200""",
        params
    )
    return _ok(rows) if ok else _err("DB error")


@app.get("/api/test-runs/<int:rid>")
def get_test_run(rid):
    ok, rows = run_query(
        """SELECT r.*, p.name AS procedure_name, p.doc_id
           FROM lab.test_runs r
           JOIN lab.test_procedures p ON p.id=r.procedure_id
           WHERE r.id=%s""",
        (rid,)
    )
    if not ok or not rows:
        return _err("Not found", 404)
    run_rec = rows[0]
    _, responses = run_query(
        "SELECT * FROM lab.test_run_responses WHERE run_id=%s ORDER BY id",
        (rid,)
    )
    run_rec["responses"] = responses
    # Include procedure sections+steps so the detail view needs one API call
    _, sections = run_query(
        "SELECT * FROM lab.test_proc_sections WHERE procedure_id=%s ORDER BY order_index",
        (run_rec["procedure_id"],)
    )
    for sec in sections:
        _, steps = run_query(
            "SELECT * FROM lab.test_proc_steps WHERE section_id=%s ORDER BY order_index",
            (sec["id"],)
        )
        sec["steps"] = steps
    run_rec["sections"] = sections
    return _ok(run_rec)


@app.post("/api/test-runs")
def create_test_run():
    b = request.json or {}
    ok, run_rec = run_write(
        """INSERT INTO lab.test_runs
           (procedure_id, serial_number, model_number, test_location, technician_name, status)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
        (b["procedure_id"], b.get("serial_number"), b.get("model_number"),
         b.get("test_location"), b.get("technician_name"),
         b.get("status", "in_progress"))
    )
    if not ok:
        return _err(run_rec.get("error", "DB error"))
    run_id = run_rec["id"]
    for resp in b.get("responses", []):
        run_write(
            """INSERT INTO lab.test_run_responses
               (run_id, step_id, value, auto_generated, passed)
               VALUES (%s,%s,%s,%s,%s)""",
            (run_id, resp["step_id"], str(resp.get("value", "")),
             resp.get("auto_generated", False), resp.get("passed")),
            returning=False,
        )
    return _ok(run_rec, 201)


@app.patch("/api/test-runs/<int:rid>")
def update_test_run(rid):
    b = request.json or {}
    allowed = {"status", "serial_number", "model_number", "test_location", "technician_name"}
    sets, params = [], []
    for k, v in b.items():
        if k in allowed:
            sets.append(f"{k}=%s"); params.append(v)
    if not sets:
        return _err("No valid fields")
    sets.append("updated_at=NOW()")
    params.append(rid)
    ok, row = run_write(
        f"UPDATE lab.test_runs SET {', '.join(sets)} WHERE id=%s RETURNING *", params
    )
    return _ok(row) if ok else _err(row.get("error", ""))


@app.get("/api/test-runs/summary")
def test_runs_summary():
    """Aggregate test run pass/fail for the past 7 days, grouped by procedure."""
    _, totals = run_query("""
        SELECT
            COUNT(*)                                                               AS total,
            SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END)                   AS passed,
            SUM(CASE WHEN status='failed'    THEN 1 ELSE 0 END)                   AS failed,
            ROUND(100.0 * SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END)
                  / NULLIF(COUNT(*), 0), 1)                                        AS pass_rate
        FROM lab.test_runs
        WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
          AND status IN ('completed', 'failed')
    """)
    _, by_product = run_query("""
        SELECT p.id   AS procedure_id,
               p.name AS procedure_name,
               p.product_type,
               COUNT(*)                                                            AS total,
               SUM(CASE WHEN r.status='completed' THEN 1 ELSE 0 END)              AS passed,
               SUM(CASE WHEN r.status='failed'    THEN 1 ELSE 0 END)              AS failed,
               ROUND(100.0 * SUM(CASE WHEN r.status='completed' THEN 1 ELSE 0 END)
                     / NULLIF(COUNT(*), 0), 1)                                     AS pass_rate
        FROM lab.test_runs r
        JOIN lab.test_procedures p ON p.id = r.procedure_id
        WHERE r.created_at >= CURRENT_DATE - INTERVAL '7 days'
          AND r.status IN ('completed', 'failed')
        GROUP BY p.id, p.name, p.product_type
        ORDER BY failed DESC, total DESC
    """)
    _, trend = run_query("""
        SELECT DATE(created_at)::text AS day,
               COUNT(*)               AS total,
               SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS passed,
               SUM(CASE WHEN status='failed'    THEN 1 ELSE 0 END) AS failed
        FROM lab.test_runs
        WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
          AND status IN ('completed', 'failed')
        GROUP BY DATE(created_at)
        ORDER BY day
    """)
    return _ok({
        "totals":     totals[0] if totals else {},
        "by_product": by_product,
        "trend":      trend,
    })


def _load_json_field(v):
    """Safely parse a JSONB field that may come back as str or dict/list."""
    if isinstance(v, str):
        return json.loads(v) if v else {}
    return v if v is not None else {}


def _auto_generate_step_value(step):
    """Return (value, passed) for a single step, generating a passing value."""
    stype = step["step_type"]
    tol   = _load_json_field(step.get("tolerances_json"))
    opts  = _load_json_field(step.get("options_json"))
    if not isinstance(opts, list):
        opts = []

    if stype == "instruction":
        return None, None
    if stype == "ok_check":
        return "OK", True
    if stype == "pass_fail":
        return "Pass", True
    if stype == "radio":
        return (opts[0] if opts else "Option 1"), True
    if stype == "text":
        return "Verified by technician", True
    if stype == "photo":
        return "Photo captured", True
    if stype in ("number", "auto_number"):
        lower   = tol.get("lower")
        upper   = tol.get("upper")
        nominal = tol.get("nominal")
        if lower is None and upper is None:
            return "0", True
        lo  = float(lower)  if lower   is not None else 0.0
        hi  = float(upper)  if upper   is not None else 100.0
        nom = float(nominal) if nominal is not None else (lo + hi) / 2.0
        rng = hi - lo
        variance = rng * 0.3
        raw = nom + _rnd.uniform(-variance, variance)
        safe_lo = lo + rng * 0.04
        safe_hi = hi - rng * 0.04
        val = max(safe_lo, min(safe_hi, raw))
        # Use integer if range is 10 or less and bounds are whole numbers
        if rng <= 10 and lo == int(lo) and hi == int(hi):
            val = int(round(val))
        else:
            val = round(val, 2)
        return val, True
    return None, None


def _auto_generate_step_value_failing(step):
    """Return (value, passed=False) — a realistic value that FAILS this step."""
    stype = step["step_type"]
    tol   = _load_json_field(step.get("tolerances_json"))
    opts  = _load_json_field(step.get("options_json"))
    if not isinstance(opts, list):
        opts = []

    if stype == "instruction":
        return None, None
    if stype == "ok_check":
        # ok_check is a checklist item — can't really fail, keep passing
        return "OK", True
    if stype == "pass_fail":
        return "Fail", False
    if stype == "radio":
        # Radio just picks an option — no numeric tolerance to violate
        return (opts[0] if opts else "Option 1"), True
    if stype == "text":
        # Text fields don't have pass/fail logic
        return "Anomaly detected — flagged for supervisor review", True
    if stype in ("number", "auto_number"):
        lower = tol.get("lower")
        upper = tol.get("upper")
        if lower is None and upper is None:
            return "0", False
        lo  = float(lower) if lower is not None else 0.0
        hi  = float(upper) if upper is not None else 100.0
        rng = hi - lo
        # Generate a value clearly outside tolerance: 5–20% beyond bound
        if _rnd.random() < 0.5:
            val = lo - rng * _rnd.uniform(0.05, 0.20)  # below lower
        else:
            val = hi + rng * _rnd.uniform(0.05, 0.20)  # above upper
        if rng <= 10 and lo == int(lo) and hi == int(hi):
            val = int(round(val))
        else:
            val = round(val, 2)
        return val, False
    return None, None


def _generate_run_responses(run_id, procedure_id, status):
    """Generate step responses for a seeded run. Failed runs get 1–2 failing steps."""
    _, sections = run_query(
        "SELECT * FROM lab.test_proc_sections WHERE procedure_id=%s ORDER BY order_index",
        (procedure_id,)
    )
    # Collect all non-instruction steps
    all_steps = []
    for sec in sections:
        _, steps = run_query(
            "SELECT * FROM lab.test_proc_steps WHERE section_id=%s ORDER BY order_index",
            (sec["id"],)
        )
        for step in steps:
            if step["step_type"] != "instruction":
                all_steps.append(step)

    if not all_steps:
        return

    # For failed runs: choose 1–2 steps to force-fail (prefer pass_fail / numeric types)
    fail_step_ids: set = set()
    if status == "failed":
        candidates = [s for s in all_steps
                      if s["step_type"] in ("pass_fail", "number", "auto_number")]
        if not candidates:
            candidates = all_steps
        n_fail = _rnd.randint(1, min(2, len(candidates)))
        for s in _rnd.sample(candidates, n_fail):
            fail_step_ids.add(s["id"])

    for step in all_steps:
        if step["id"] in fail_step_ids:
            val, passed = _auto_generate_step_value_failing(step)
        else:
            val, passed = _auto_generate_step_value(step)
        if val is None:
            continue
        run_write(
            """INSERT INTO lab.test_run_responses
               (run_id, step_id, value, auto_generated, passed)
               VALUES (%s,%s,%s,%s,%s)""",
            (run_id, step["id"], str(val), True, passed),
            returning=False,
        )


@app.post("/api/test-runs/generate-all")
def generate_all_test_run_data():
    """Batch-generate response data for every run that has no responses yet."""
    ok, runs_without = run_query("""
        SELECT r.id, r.procedure_id, r.status
        FROM lab.test_runs r
        WHERE NOT EXISTS (
            SELECT 1 FROM lab.test_run_responses rr WHERE rr.run_id = r.id
        )
        ORDER BY r.id
        LIMIT 300
    """)
    if not ok:
        return _err("DB error")
    count = 0
    for run in (runs_without or []):
        _generate_run_responses(run["id"], run["procedure_id"], run["status"])
        count += 1
    return _ok({"populated": count})


@app.post("/api/test-runs/<int:rid>/generate")
def generate_test_run_data(rid):
    """Auto-generate passing response data for every step in a test run."""
    ok, runs = run_query("SELECT * FROM lab.test_runs WHERE id=%s", (rid,))
    if not ok or not runs:
        return _err("Not found", 404)
    run_rec = runs[0]

    _, sections = run_query(
        "SELECT * FROM lab.test_proc_sections WHERE procedure_id=%s ORDER BY order_index",
        (run_rec["procedure_id"],)
    )

    # Clear any existing responses
    run_write("DELETE FROM lab.test_run_responses WHERE run_id=%s", (rid,), returning=False)

    generated = 0
    for sec in sections:
        _, steps = run_query(
            "SELECT * FROM lab.test_proc_steps WHERE section_id=%s ORDER BY order_index",
            (sec["id"],)
        )
        for step in steps:
            val, passed = _auto_generate_step_value(step)
            if val is None:
                continue
            run_write(
                """INSERT INTO lab.test_run_responses
                   (run_id, step_id, value, auto_generated, passed)
                   VALUES (%s,%s,%s,%s,%s)""",
                (rid, step["id"], str(val), True, passed),
                returning=False,
            )
            generated += 1

    run_write(
        "UPDATE lab.test_runs SET status='completed', updated_at=NOW() WHERE id=%s",
        (rid,), returning=False,
    )
    return _ok({"generated": generated})


# ── Test Run Images ────────────────────────────────────────────────────────────
@app.get("/api/test-runs/<int:rid>/images")
def list_run_images(rid):
    ok, rows = run_query(
        "SELECT id, run_id, step_id, section_id, filename, mime_type, data_b64, caption, created_at "
        "FROM lab.test_run_images WHERE run_id=%s ORDER BY created_at",
        (rid,)
    )
    return _ok(rows) if ok else _err("DB error")


@app.post("/api/test-runs/<int:rid>/images")
def upload_run_image(rid):
    b = request.json or {}
    if not b.get("data_b64"):
        return _err("data_b64 is required")
    ok, row = run_write(
        """INSERT INTO lab.test_run_images
           (run_id, step_id, section_id, filename, mime_type, data_b64, caption)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id, run_id, step_id, section_id, filename, mime_type, caption, created_at""",
        (rid, b.get("step_id"), b.get("section_id"), b.get("filename", "photo.jpg"),
         b.get("mime_type", "image/jpeg"), b["data_b64"], b.get("caption")),
    )
    return _ok(row, 201) if ok else _err(row.get("error", "DB error"))


@app.delete("/api/test-run-images/<int:iid>")
def delete_run_image(iid):
    ok, row = run_write(
        "DELETE FROM lab.test_run_images WHERE id=%s RETURNING id", (iid,)
    )
    return _ok(row) if ok else _err(row.get("error", ""))


# ── Procedure Step Reference Images ────────────────────────────────────────────
@app.post("/api/proc-steps/<int:sid>/images")
def upload_proc_step_image(sid):
    b = request.json or {}
    if not b.get("data_b64"):
        return _err("data_b64 is required")
    ok, row = run_write(
        """INSERT INTO lab.test_proc_step_images (step_id, filename, mime_type, data_b64)
           VALUES (%s,%s,%s,%s) RETURNING id, step_id, filename, mime_type, data_b64""",
        (sid, b.get("filename", "photo.jpg"), b.get("mime_type", "image/jpeg"), b["data_b64"]),
    )
    return _ok(row, 201) if ok else _err(row.get("error", "DB error"))


@app.delete("/api/proc-step-images/<int:iid>")
def delete_proc_step_image(iid):
    ok, row = run_write(
        "DELETE FROM lab.test_proc_step_images WHERE id=%s RETURNING id", (iid,)
    )
    return _ok(row) if ok else _err(row.get("error", ""))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5002)), debug=True)
