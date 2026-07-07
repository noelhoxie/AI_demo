-- Airtech Lab Intelligence Platform — Write-back schema
-- Run against the PostgreSQL instance configured in LAB_DB_URL

CREATE SCHEMA IF NOT EXISTS lab;

-- Lab technicians
CREATE TABLE IF NOT EXISTS lab.technicians (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    badge_id    VARCHAR(50)  UNIQUE,
    specialty   VARCHAR(100),
    email       VARCHAR(150),
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- Reading enhancements (manual overlay on bronze layer readings)
CREATE TABLE IF NOT EXISTS lab.reading_enhancements (
    id                  SERIAL PRIMARY KEY,
    bronze_reading_id   VARCHAR(100) NOT NULL,
    machine_id          VARCHAR(100),
    technician_id       INTEGER REFERENCES lab.technicians(id),
    visual_inspection   TEXT,
    anomalies_noted     TEXT,
    corrective_actions  TEXT,
    override_values     JSONB    DEFAULT '{}',
    manual_measurements JSONB    DEFAULT '[]',
    confidence_in_data  INTEGER  CHECK (confidence_in_data BETWEEN 1 AND 5),
    notes               TEXT,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_enhancements_reading_id
    ON lab.reading_enhancements (bronze_reading_id);

-- AI predictions (one per reading, upserted)
CREATE TABLE IF NOT EXISTS lab.predictions (
    id                   SERIAL PRIMARY KEY,
    bronze_reading_id    VARCHAR(100) NOT NULL UNIQUE,
    machine_id           VARCHAR(100),
    success_probability  NUMERIC(5,2),
    risk_level           VARCHAR(20),
    risk_factors         JSONB DEFAULT '[]',
    recommendations      JSONB DEFAULT '[]',
    reasoning            TEXT,
    model_version        VARCHAR(100),
    raw_response         TEXT,
    generated_at         TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_predictions_reading_id
    ON lab.predictions (bronze_reading_id);

-- Upcoming test schedule / leaderboard queue
CREATE TABLE IF NOT EXISTS lab.test_schedule (
    id                      SERIAL PRIMARY KEY,
    title                   VARCHAR(200) NOT NULL,
    sample_id               VARCHAR(100),
    reading_id              VARCHAR(100),   -- linked bronze reading (optional)
    machine_id              VARCHAR(100),
    test_type               VARCHAR(100),
    scheduled_at            TIMESTAMP,
    estimated_duration_min  INTEGER DEFAULT 60,
    priority                VARCHAR(20) DEFAULT 'normal'
                                CHECK (priority IN ('critical','high','normal','low')),
    technician_id           INTEGER REFERENCES lab.technicians(id),
    status                  VARCHAR(30) DEFAULT 'scheduled'
                                CHECK (status IN ('scheduled','in_progress','completed','cancelled')),
    started_at              TIMESTAMP,
    completed_at            TIMESTAMP,
    notes                   TEXT,
    created_at              TIMESTAMP DEFAULT NOW(),
    updated_at              TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_schedule_status
    ON lab.test_schedule (status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_schedule_technician
    ON lab.test_schedule (technician_id);

-- Seed: demo technicians
INSERT INTO lab.technicians (name, badge_id, specialty, email) VALUES
    ('Marcus Webb',     'AT-101', 'Pressure & Leak Testing',     'mwebb@airtech.com'),
    ('Priya Nair',      'AT-102', 'Flow Performance Testing',    'pnair@airtech.com'),
    ('Carlos Fuentes',  'AT-103', 'Mechanical Inspection',       'cfuentes@airtech.com'),
    ('Dana Holloway',   'AT-104', 'Electrical & Vibration',      'dholloway@airtech.com'),
    ('James Okafor',    'AT-105', 'Final Acceptance Testing',    'jokafor@airtech.com')
ON CONFLICT DO NOTHING;

-- Seed: demo upcoming tests
INSERT INTO lab.test_schedule
    (title, sample_id, machine_id, test_type, scheduled_at, estimated_duration_min, priority, technician_id)
SELECT
    titles.title, titles.sample_id, titles.machine_id, titles.test_type,
    NOW() + (titles.offset_min * INTERVAL '1 minute'),
    titles.est_min, titles.priority,
    (SELECT id FROM lab.technicians WHERE badge_id=titles.badge LIMIT 1)
FROM (VALUES
    ('Leak Test — P300-HPC SN-1042',   'SN-1042', 'machine_pressure', 'leak_test',         10,  45, 'critical', 'AT-101'),
    ('Flow Perf — F200-STD SN-2071',   'SN-2071', 'machine_flow',     'flow_performance',  25,  60, 'high',     'AT-102'),
    ('Pressure Test — P500-LPX SN-1088','SN-1088','machine_pressure', 'pressure_test',     60,  30, 'normal',   'AT-101'),
    ('Vibration Check — F400-PRO SN-2099','SN-2099','machine_flow',   'vibration_test',    90,  45, 'high',     'AT-104'),
    ('Leak Test — P100-ECO SN-1055',   'SN-1055', 'machine_pressure', 'leak_test',        120,  45, 'normal',   'AT-103'),
    ('Final Accept — P300-HPC SN-1019','SN-1019', 'machine_pressure', 'acceptance',       150,  90, 'critical', 'AT-105'),
    ('Flow Perf — F200-STD SN-2034',   'SN-2034', 'machine_flow',     'flow_performance', 180,  60, 'normal',   'AT-102'),
    ('Pressure Test — P500-LPX SN-1077','SN-1077','machine_pressure', 'pressure_test',    210,  30, 'low',      'AT-103'),
    ('Vibration — F400-PRO SN-2088',   'SN-2088', 'machine_flow',     'vibration_test',   240,  45, 'normal',   'AT-104'),
    ('Final Accept — F200-STD SN-2012','SN-2012', 'machine_flow',     'acceptance',       270,  90, 'high',     'AT-105')
) AS titles(title, sample_id, machine_id, test_type, offset_min, est_min, priority, badge)
ON CONFLICT DO NOTHING;
