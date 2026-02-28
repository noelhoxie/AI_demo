# QAD Manufacturing Pipeline — Bronze, Silver, Gold (OEE)

Pipeline for ingesting QAD manufacturing data and computing **Overall Equipment Effectiveness (OEE)** for a Novelis-style aluminum producer: **5 machine centers** across **3 facilities**. Bronze layer uses **QAD base table** names and field conventions.

## Facilities and machine centers

| Facility     | Machine centers   |
|-------------|-------------------|
| Oswego      | Hot Mill 1, Caster 1 |
| Kennesaw    | Cold Mill 1, Coating Line 1 |
| Nachterstedt| Slitter 1 |

## Layers

### Bronze (QAD base tables)

Bronze tables mirror QAD ERP base table names and key fields:

| Table   | QAD base table | Description | Key fields |
|--------|----------------|-------------|------------|
| **wo_mst** | Work Order Master | Work order header | wono, site, line, part, qty_ord, ord_status, start_date, due_date, cr_date |
| **jt_mst** | Job Ticket Master | Production completions / labor reporting | ticket_id, wono, site, line, good_qty, scrap_qty, start_ts, end_ts |
| **dt_mst** | Downtime Master | Machine downtime events | event_id, site, line, start_ts, end_ts, reason_code, reason_desc |

Ingest notebook simulates QAD export; replace with read from your QAD landing path or JDBC/API.

### Silver (production data)

- **qad_silver_production_events** — From **jt_mst** + **wo_mst** (join on wono): ticket_id, wono, facility, machine_center, good_qty, scrap_qty, run_time_seconds, material, planned_qty, wo_status.
- **qad_silver_downtime_events** — From **dt_mst**: event_id, facility, machine_center, start_ts, end_ts, duration_minutes, reason_code, reason_desc.
- **qad_silver_machine_center_daily** — Daily aggregates by facility/machine_center for OEE.

### Gold (OEE)

- **qad_gold_oee_by_machine_center** — OEE by facility, machine_center, production_date (availability, performance, quality, oee).
- **qad_gold_oee_latest** — View: latest OEE row per machine center for dashboards.

## Running the pipeline

```bash
databricks bundle run -t dev qad_oee_pipeline
```

Or in the workspace: **Workflows → Jobs → QAD OEE Pipeline → Run now**.

Tasks: **qad_bronze_ingest** (wo_mst, jt_mst, dt_mst) → **qad_silver_production** → **qad_gold_oee**.

## Catalog and schema

Uses bundle variables `catalog` and `schema` (e.g. `serverless_hadnqm_catalog`, `ai_sc_test`). Bronze tables **wo_mst**, **jt_mst**, **dt_mst** and silver/gold tables live in that schema.
