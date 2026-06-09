# Databricks notebook source
# MAGIC %md
# MAGIC # Gold — gold_demand_forecast
# MAGIC 12-month historical actuals + 12-month forward forecast by SKU.
# MAGIC Columns: sku_id, sku_description, category, plant, period (YYYY-MM),
# MAGIC period_label, is_forecast, forecast_qty, actual_qty, forecast_value_usd,
# MAGIC mape, bias_pct, confidence_lower, confidence_upper, forecast_method, avg_selling_price

# COMMAND ----------

dbutils.widgets.text("catalog", "demo_nah_catalog", "Catalog")
dbutils.widgets.text("schema", "supplychain_solutionstudio", "Schema")
catalog = (dbutils.widgets.get("catalog") or "demo_nah_catalog").strip()
schema  = (dbutils.widgets.get("schema")  or "supplychain_solutionstudio").strip()
print(f"Using catalog={catalog}, schema={schema}")

# COMMAND ----------

import random
from pyspark.sql.types import (
    StructType, StructField, StringType, BooleanType,
    IntegerType, DoubleType
)

# SKU definitions — aligned with app.py and gold_inventory data
_skus = [
    {"sku": "FG-55102", "desc": "Hydraulic Pump Unit",        "cat": "Finished Goods",  "plant": "ORD", "base": 820,  "trend": 0.010, "mape": 34.2, "bias": -0.28, "vol": 0.06, "asp": 499.00},
    {"sku": "FG-78421", "desc": "Premium Sprocket Assembly",  "cat": "Finished Goods",  "plant": "RTM", "base": 1150, "trend": 0.006, "mape": 28.7, "bias":  0.22, "vol": 0.05, "asp": 235.00},
    {"sku": "CP-33901", "desc": "Control Module Type C",      "cat": "Components",      "plant": "SIN", "base": 3200, "trend": 0.008, "mape": 24.1, "bias": -0.19, "vol": 0.04, "asp":  88.50},
    {"sku": "RM-44211", "desc": "Titanium Sheet 2mm",         "cat": "Raw Materials",   "plant": "DFW", "base": 600,  "trend": 0.005, "mape": 21.8, "bias":  0.18, "vol": 0.05, "asp":  67.00},
    {"sku": "FG-91033", "desc": "Drive Belt Assembly XL",     "cat": "Finished Goods",  "plant": "MTY", "base": 2650, "trend": 0.009, "mape": 19.4, "bias": -0.16, "vol": 0.04, "asp":  24.00},
    {"sku": "PKG-2201", "desc": "Corrugated Box 48x36",       "cat": "Packaging",       "plant": "ORD", "base": 5200, "trend": 0.003, "mape":  7.8, "bias": -0.01, "vol": 0.03, "asp":   3.20},
    {"sku": "WIP-7742", "desc": "Sub-Assembly Module B",      "cat": "Work in Progress","plant": "MTY", "base": 420,  "trend": 0.007, "mape": 15.2, "bias":  0.08, "vol": 0.05, "asp": 182.00},
    {"sku": "RM-34892", "desc": "Alloy Steel Rod 25mm",       "cat": "Raw Materials",   "plant": "RTM", "base": 890,  "trend": 0.004, "mape": 18.3, "bias":  0.14, "vol": 0.06, "asp":  48.00},
    {"sku": "FG-44901", "desc": "Precision Gear Assembly",    "cat": "Finished Goods",  "plant": "SIN", "base": 1680, "trend": 0.007, "mape": 12.6, "bias": -0.05, "vol": 0.04, "asp": 312.00},
    {"sku": "CP-78820", "desc": "Sensor Array Module",        "cat": "Components",      "plant": "ORD", "base": 2100, "trend": 0.011, "mape": 16.8, "bias":  0.09, "vol": 0.05, "asp":  74.00},
]

_hist_months = [
    ("2024-06", "Jun-24"), ("2024-07", "Jul-24"), ("2024-08", "Aug-24"),
    ("2024-09", "Sep-24"), ("2024-10", "Oct-24"), ("2024-11", "Nov-24"),
    ("2024-12", "Dec-24"), ("2025-01", "Jan-25"), ("2025-02", "Feb-25"),
    ("2025-03", "Mar-25"), ("2025-04", "Apr-25"), ("2025-05", "May-25"),
]
_fwd_months = [
    ("2025-06", "Jun-25"), ("2025-07", "Jul-25"), ("2025-08", "Aug-25"),
    ("2025-09", "Sep-25"), ("2025-10", "Oct-25"), ("2025-11", "Nov-25"),
    ("2025-12", "Dec-25"), ("2026-01", "Jan-26"), ("2026-02", "Feb-26"),
    ("2026-03", "Mar-26"), ("2026-04", "Apr-26"), ("2026-05", "May-26"),
]

_seasonal = {
    "Jan": 0.84, "Feb": 0.87, "Mar": 0.93, "Apr": 0.97,
    "May": 1.00, "Jun": 0.96, "Jul": 0.91, "Aug": 0.95,
    "Sep": 1.01, "Oct": 1.06, "Nov": 1.09, "Dec": 1.13,
}

rows = []
rng  = random.Random(20240601)

for sd in _skus:
    asp = sd["asp"]

    # ── Historical (actuals known) ──────────────────────────────────────────
    for i, (period, label) in enumerate(_hist_months):
        seasonal = _seasonal.get(label[:3], 1.0)
        actual   = round(sd["base"] * (1 + i * sd["trend"]) * seasonal
                         * (1 + (rng.random() - 0.5) * sd["vol"]))
        forecast = round(actual * (1 + sd["bias"] + (rng.random() - 0.5) * 0.06))
        err      = abs(forecast - actual) / actual * 100
        bias_pct = (forecast - actual) / actual * 100
        ci       = round(forecast * 0.10)
        rows.append((
            sd["sku"], sd["desc"], sd["cat"], sd["plant"],
            period, label, False,
            forecast, actual, round(actual * asp, 2),
            round(err, 1), round(bias_pct, 1),
            max(0, forecast - ci), forecast + ci,
            "Statistical", round(asp, 2),
        ))

    # ── Forward forecast (actuals unknown) ─────────────────────────────────
    last_i   = len(_hist_months) - 1
    last_base = sd["base"] * (1 + last_i * sd["trend"])
    for i, (period, label) in enumerate(_fwd_months):
        seasonal = _seasonal.get(label[:3], 1.0)
        fwd_qty  = last_base * (1 + (last_i + 1 + i) * sd["trend"]) * seasonal
        forecast = round(fwd_qty * (1 + (rng.random() - 0.5) * 0.03))
        # Confidence interval widens as horizon extends
        ci       = round(forecast * (0.08 + i * 0.012))
        method   = "Consensus" if i < 3 else ("Statistical" if i < 9 else "Long-Range")
        rows.append((
            sd["sku"], sd["desc"], sd["cat"], sd["plant"],
            period, label, True,
            forecast, None, round(forecast * asp, 2),
            None, None,
            max(0, forecast - ci), forecast + ci,
            method, round(asp, 2),
        ))

schema_def = StructType([
    StructField("sku_id",              StringType(),  True),
    StructField("sku_description",     StringType(),  True),
    StructField("category",            StringType(),  True),
    StructField("plant",               StringType(),  True),
    StructField("period",              StringType(),  True),  # YYYY-MM
    StructField("period_label",        StringType(),  True),  # Jun-24
    StructField("is_forecast",         BooleanType(), True),  # false=historical, true=forward
    StructField("forecast_qty",        IntegerType(), True),
    StructField("actual_qty",          IntegerType(), True),  # null for forward periods
    StructField("forecast_value_usd",  DoubleType(),  True),
    StructField("mape",                DoubleType(),  True),  # null for forward periods
    StructField("bias_pct",            DoubleType(),  True),  # null for forward periods
    StructField("confidence_lower",    IntegerType(), True),
    StructField("confidence_upper",    IntegerType(), True),
    StructField("forecast_method",     StringType(),  True),
    StructField("avg_selling_price",   DoubleType(),  True),
])

from pyspark.sql import functions as F
from pyspark.sql.window import Window

df = spark.createDataFrame(rows, schema_def)

# ── Deduplicate: keep one canonical sku_id per sku_description ──────────────
# For each description, pick the lexicographically first sku_id across all periods
w = Window.partitionBy("sku_description").orderBy("sku_id")
df_before = df.count()
df = df.withColumn("_rn", F.row_number().over(w)).filter(F.col("_rn") == 1).drop("_rn")
df_after = df.count()
print(f"Deduplication: {df_before} → {df_after} rows ({df_before - df_after} removed as exact description duplicates)")

df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"`{catalog}`.`{schema}`.gold_demand_forecast"
)
print(f"Wrote {df.count()} rows to gold_demand_forecast")
display(df.orderBy("sku_id", "period").limit(30))
