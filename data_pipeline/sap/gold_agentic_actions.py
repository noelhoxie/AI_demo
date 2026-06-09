# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — gold_agentic_actions
# MAGIC Recommended supply chain actions seeded from current operational state.
# MAGIC Each row represents a discrete, executable action with impact quantification.
# MAGIC Columns: action_id, action_type, entity_type, entity_id, entity_name,
# MAGIC description, rationale, impact_usd, priority, status, owner, due_date

# COMMAND ----------

dbutils.widgets.text("catalog", "demo_nah_catalog", "Catalog")
dbutils.widgets.text("schema", "supplychain_solutionstudio", "Schema")
catalog = (dbutils.widgets.get("catalog") or "demo_nah_catalog").strip()
schema  = (dbutils.widgets.get("schema")  or "supplychain_solutionstudio").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

from datetime import date, timedelta
from pyspark.sql.types import (
    StructType, StructField, StringType, LongType
)

today = date.today()

rows = [
    # ── Inventory / Stockout ──────────────────────────────────────────────────
    (
        "ACT-001", "emergency_reorder", "sku", "FG-55102", "Hydraulic Pump Unit",
        "Trigger emergency reorder for FG-55102 — 4 DOS remaining in Chicago DC, below 7-day safety threshold.",
        "Systematic under-forecast bias of -28% has depleted safety stock. 3 Apex Industrial orders currently on hold. $421K revenue exposure if not resolved within 48h.",
        421000, "Critical", "pending", "Supply Chain Ops",
        str(today + timedelta(days=1)),
    ),
    (
        "ACT-002", "lateral_transfer", "sku", "FG-78421", "Premium Sprocket Assembly",
        "Transfer 200 units FG-78421 from Chicago DC to Rotterdam DC to relieve 91% warehouse utilization.",
        "Chicago DC has 187 DOS of FG-78421 (excess). Rotterdam DC at 91% capacity. Lateral transfer recovers $284K of stranded excess and frees Rotterdam capacity.",
        284000, "High", "pending", "Logistics",
        str(today + timedelta(days=2)),
    ),
    (
        "ACT-008", "safety_stock_review", "sku", "FG-91033", "Drive Belt Assembly XL",
        "Review and increase safety stock policy for FG-91033 — currently 3 DOS in Singapore DC, below 7-day at-risk threshold.",
        "Drive Belt Assembly XL at near-stockout. Singapore DC. 19.4% MAPE with -16.7% under-forecast bias. $67K revenue exposure.",
        67000, "Medium", "pending", "Supply Planning",
        str(today + timedelta(days=2)),
    ),

    # ── Procurement / PO Exceptions ───────────────────────────────────────────
    (
        "ACT-003", "update_contract", "supplier", "PSUP-PACIFIC", "Pacific Components",
        "Load renewed Q2 rate card into ERP for Pacific Components (Item: PSUP-CONTRACT-2024-Q2) to auto-resolve 18 held POs.",
        "18 POs held totalling $143K. ERP still applying expired Q1 price ($41.20) vs agreed Q2 rate ($38.50). Contract load auto-resolves all 18 within minutes.",
        143000, "High", "pending", "Procurement",
        str(today + timedelta(days=1)),
    ),
    (
        "ACT-004", "expedite_shipment", "po", "PO-91207", "EuroTech Supplies — Pump Assembly F",
        "Switch PO-91207 carrier from sea to air freight — Rotterdam port backlog causing 6-day delivery delay.",
        "Air freight premium ~$2.1K vs $14K stockout risk on Pump Assembly F. Vessel delayed; switching to air resolves on-time delivery.",
        14000, "High", "pending", "Logistics",
        str(today + timedelta(days=1)),
    ),
    (
        "ACT-005", "post_goods_receipt", "po", "PO-84029", "Allied Materials — Actuator M",
        "Post goods receipt for PO-84029 in ERP — goods confirmed in WH-01, warehouse receipt not yet posted.",
        "Unblocks invoice INV-AP-8841 ($38K) for automated 3-way match and payment. Goods physically present for 9 days.",
        38000, "Medium", "pending", "Warehouse Ops",
        str(today + timedelta(days=1)),
    ),
    (
        "ACT-007", "dual_source", "sku", "CP-33901", "Control Module Type C",
        "Initiate dual-source RFQ for CP-33901 and DA-410 to reduce single-source dependency on Pacific Components.",
        "Pacific Components short-shipped 4 POs (8–22% below ordered quantity). $218K exposure from single-source risk. RFQ to 2 alternative suppliers within 48h.",
        218000, "Medium", "pending", "Procurement",
        str(today + timedelta(days=5)),
    ),
    (
        "ACT-010", "fx_rate_refresh", "supplier", "PSUP-PRECISION", "Precision Parts GmbH",
        "Run FX rate refresh job for EUR-denominated POs from Precision Parts GmbH to resolve 3 held invoices.",
        "3 POs held due to EUR/USD FX mismatch (converted at 1.072 vs PO rate 1.089). Daily FX feed not yet applied. Auto-resolves on next feed run.",
        23500, "Low", "pending", "Finance",
        str(today + timedelta(days=1)),
    ),

    # ── Demand / Forecast ─────────────────────────────────────────────────────
    (
        "ACT-006", "adjust_forecast", "sku", "FG-55102", "Hydraulic Pump Unit",
        "Apply +28% upward override to FG-55102 consensus forecast to correct persistent under-forecast bias.",
        "34.2% MAPE with -28% systematic bias identified over 12 months. Correcting forecast improves safety stock calculations and prevents recurrent stockouts.",
        0, "Medium", "pending", "Demand Planning",
        str(today + timedelta(days=3)),
    ),

    # ── S&OP / IBP ────────────────────────────────────────────────────────────
    (
        "ACT-009", "capacity_escalation", "bu", "EMEA", "EMEA Business Unit",
        "Escalate EMEA Q3 capacity shortfall to S&OP Executive Review — current attainment 88.7% vs 92% target.",
        "$4.2M revenue at risk. Issue must be resolved before May 12 Consensus Meeting to prevent it surfacing at Executive Sign-off on May 14.",
        4200000, "High", "pending", "S&OP",
        str(today + timedelta(days=2)),
    ),
]

schema_def = StructType([
    StructField("action_id",    StringType(), False),
    StructField("action_type",  StringType(), True),
    StructField("entity_type",  StringType(), True),
    StructField("entity_id",    StringType(), True),
    StructField("entity_name",  StringType(), True),
    StructField("description",  StringType(), True),
    StructField("rationale",    StringType(), True),
    StructField("impact_usd",   LongType(),   True),
    StructField("priority",     StringType(), True),
    StructField("status",       StringType(), True),
    StructField("owner",        StringType(), True),
    StructField("due_date",     StringType(), True),
])

df = spark.createDataFrame(rows, schema_def)
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.gold_agentic_actions"
)
print(f"Wrote {df.count()} rows to gold_agentic_actions")
display(df)
