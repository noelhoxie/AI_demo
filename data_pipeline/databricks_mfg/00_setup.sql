-- ============================================================
-- DATABRICKS MANUFACTURING PIPELINE — SETUP
-- Run once before any pipeline steps.
-- Creates catalog, schemas, and the machine master reference table.
-- ============================================================


USE CATALOG demo_nah_catalog;

CREATE SCHEMA IF NOT EXISTS mfg_bronze
  COMMENT 'Raw ingested data — immutable, append-only. Never update or delete.';

CREATE SCHEMA IF NOT EXISTS mfg_silver
  COMMENT 'Validated, enriched, deduplicated operational records.';

CREATE SCHEMA IF NOT EXISTS mfg_gold
  COMMENT 'Aggregated, app-ready metrics. Source of truth for the manufacturing app.';

-- ── Bronze table schemas ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mfg_bronze.machine_telemetry_raw (
  machine_id      STRING        NOT NULL COMMENT 'Machine identifier (e.g. PPU-FAB-01)',
  ts              TIMESTAMP     NOT NULL COMMENT 'Sensor reading timestamp',
  oee_pct         DOUBLE        COMMENT 'Overall Equipment Effectiveness (0-100)',
  temp_c          DOUBLE        COMMENT 'Machine temperature in Celsius',
  cycle_time_sec  DOUBLE        COMMENT 'Actual cycle time in seconds',
  power_kw        DOUBLE        COMMENT 'Power draw in kilowatts',
  units_count     INT           COMMENT 'Cumulative units produced this shift',
  ingest_ts       TIMESTAMP     COMMENT 'Pipeline ingest timestamp'
) USING DELTA
  COMMENT 'Raw IoT telemetry — one row per machine per reading interval'
  TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

CREATE TABLE IF NOT EXISTS mfg_bronze.production_events_raw (
  event_id        STRING        NOT NULL COMMENT 'Unique event ID (UUID)',
  machine_id      STRING        NOT NULL,
  event_ts        TIMESTAMP     NOT NULL COMMENT 'When state changed',
  state           STRING        COMMENT 'running | fault | idle | maintenance',
  fault_code      STRING        COMMENT 'Fault code if state=fault (e.g. E-4412)',
  fault_msg       STRING        COMMENT 'Fault description',
  idle_reason     STRING        COMMENT 'Reason if state=idle',
  maintenance_type STRING       COMMENT 'Type if state=maintenance',
  operator_id     STRING        COMMENT 'Operator who logged the event',
  ingest_ts       TIMESTAMP
) USING DELTA
  COMMENT 'Machine state change events — running/fault/idle/maintenance transitions'
  TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

CREATE TABLE IF NOT EXISTS mfg_bronze.alarm_events_raw (
  alarm_id        STRING        NOT NULL,
  machine_id      STRING        NOT NULL,
  severity        STRING        COMMENT 'CRITICAL | HIGH | MEDIUM | LOW',
  code            STRING        COMMENT 'Alarm code (e.g. E-4412)',
  message         STRING,
  category        STRING        COMMENT 'Equipment Fault | Maintenance Due | Performance | Quality Risk | Material / SW Hold',
  triggered_ts    TIMESTAMP     NOT NULL,
  acknowledged    BOOLEAN,
  ack_ts          TIMESTAMP,
  ack_by          STRING,
  impact          STRING        COMMENT 'Business impact description',
  ingest_ts       TIMESTAMP
) USING DELTA
  COMMENT 'Equipment alarms — one row per alarm event'
  TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

CREATE TABLE IF NOT EXISTS mfg_bronze.quality_inspections_raw (
  inspection_id   STRING        NOT NULL,
  unit_serial     STRING        NOT NULL COMMENT 'Unit serial number',
  machine_id      STRING        NOT NULL,
  line            STRING        COMMENT 'A | B | C',
  product         STRING        COMMENT 'PPU | DLA | GAM',
  inspection_ts   TIMESTAMP     NOT NULL,
  result          STRING        COMMENT 'pass | fail | rework',
  defect_type     STRING        COMMENT 'Null if pass. Solder Bridge, Bond Wire Short, etc.',
  shift_id        STRING        COMMENT 'e.g. 2026-05-05-D',
  ingest_ts       TIMESTAMP
) USING DELTA
  COMMENT 'Per-unit quality inspection results from AOI, functional test, and visual'
  TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

CREATE TABLE IF NOT EXISTS mfg_bronze.shift_records_raw (
  shift_id        STRING        NOT NULL COMMENT 'e.g. 2026-05-05-D',
  line            STRING        NOT NULL COMMENT 'ALL | A | B | C',
  product         STRING,
  start_ts        TIMESTAMP     NOT NULL,
  end_ts          TIMESTAMP     COMMENT 'NULL if shift is currently open',
  supervisor_id   STRING,
  target_units    INT,
  ingest_ts       TIMESTAMP
) USING DELTA
  COMMENT 'Shift records — one row per shift per line'
  TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true');

-- ── Gold: Machine Master Reference ────────────────────────────────────────────
-- Populated here once. Not updated by pipelines.

CREATE TABLE IF NOT EXISTS mfg_gold.machine_master (
  machine_id        STRING  NOT NULL,
  line              STRING,
  line_name         STRING,
  product           STRING,
  name              STRING,
  description       STRING,
  sensor_tags       ARRAY<STRING>,
  target_units_hr   INT,
  std_cycle_sec     DOUBLE
) USING DELTA
  COMMENT 'Static machine metadata — 18 machines across 3 production lines';

-- Populate machine master (idempotent)
MERGE INTO mfg_gold.machine_master AS t
USING (
  VALUES
    ('PPU-FAB-01','A','Photon Fab','PPU','Photolithography Station',
     'Deep-UV photolithography for PPU die patterning',
     array('exposure_intensity','stage_temp','alignment_score'), 420, 8.2),
    ('PPU-FAB-02','A','Photon Fab','PPU','Plasma Etch Chamber #1',
     'Reactive ion etching for PPU trace definition',
     array('plasma_power','chamber_pressure','etch_rate'), 290, 12.1),
    ('PPU-FAB-03','A','Photon Fab','PPU','Plasma Etch Chamber #2',
     'Reactive ion etching (redundant) for PPU trace definition',
     array('plasma_power','chamber_pressure','etch_rate'), 290, 12.1),
    ('PPU-FAB-04','A','Photon Fab','PPU','CVD Deposition System',
     'Chemical vapor deposition of dielectric layers',
     array('deposition_rate','precursor_flow','furnace_temp'), 160, 22.0),
    ('PPU-FAB-05','A','Photon Fab','PPU','Die Attach & Wire Bond',
     'Flip-chip die attach and gold wire bonding',
     array('bond_force','bond_temp','pull_strength'), 720, 4.8),
    ('PPU-FAB-06','A','Photon Fab','PPU','Wire Bond Calibration Cell',
     'Redundant wire bond station',
     array('bond_force','bond_temp','pull_strength'), 720, 4.8),
    ('DLK-ASM-01','B','Delta Array','DLA','SMT Auto-Insert #1',
     'Surface mount technology auto-placement for Delta Array PCBs',
     array('placement_accuracy','nozzle_pressure','feeder_count'), 540, 6.4),
    ('DLK-ASM-02','B','Delta Array','DLA','Lead-Free Reflow Oven',
     '7-zone convection reflow for Delta Array board soldering',
     array('peak_temp','ramp_rate','conveyor_speed'), 192, 18.0),
    ('DLK-ASM-03','B','Delta Array','DLA','Automated Optical Inspection',
     '2D/3D AOI for solder joint and component verification',
     array('defect_rate','false_call_rate','throughput'), 1080, 3.2),
    ('DLK-ASM-04','B','Delta Array','DLA','NVMe Firmware Flash Station',
     'Parallel NVMe firmware programming for Delta Array storage',
     array('flash_speed_mbps','verify_pass_rate','queue_depth'), 368, 9.5),
    ('DLK-ASM-05','B','Delta Array','DLA','Thermal Stress Chamber',
     'HALT/HASS thermal cycling -40C to +125C',
     array('chamber_temp','humidity','cycle_count'), 1, 3600.0),
    ('DLK-ASM-06','B','Delta Array','DLA','Final Functional Test Bench',
     'Full functional test: bandwidth, latency, error rate for Delta Arrays',
     array('read_bw_gbps','write_bw_gbps','latency_us'), 78, 45.0),
    ('GEN-INT-01','C','Genie AI','GAM','AI Chip Placement Robot',
     '6-axis robot placing Genie neural processing dies on substrate',
     array('pick_accuracy_um','cycle_time_s','gripper_force'), 648, 5.5),
    ('GEN-INT-02','C','Genie AI','GAM','Neural Core Bond Station',
     'Thermocompression bonding of Genie neural core stacks',
     array('bond_temp','bond_pressure_mpa','void_rate_pct'), 490, 7.2),
    ('GEN-INT-03','C','Genie AI','GAM','Model Flash Programmer',
     'LLM weight flashing and quantization for Genie AI Modules',
     array('flash_speed_gbps','verify_pass_rate','model_version'), 252, 14.0),
    ('GEN-INT-04','C','Genie AI','GAM','Functional Verification Rack',
     'JTAG boundary scan and functional test for Genie AI Modules',
     array('test_coverage_pct','fail_rate','jtag_chain_status'), 118, 30.0),
    ('GEN-INT-05','C','Genie AI','GAM','AI Burn-In Chamber',
     '2-hour 70C accelerated burn-in to screen early-life failures',
     array('chamber_temp','power_draw_w','fail_count'), 1, 7200.0),
    ('GEN-INT-06','C','Genie AI','GAM','Calibration & Pack Station',
     'Final calibration, labeling, and packaging for Genie AI Modules',
     array('calibration_score','label_accuracy','pack_rate'), 320, 11.0)
  AS src(machine_id, line, line_name, product, name, description,
         sensor_tags, target_units_hr, std_cycle_sec)
) AS s ON t.machine_id = s.machine_id
WHEN NOT MATCHED THEN INSERT *;
