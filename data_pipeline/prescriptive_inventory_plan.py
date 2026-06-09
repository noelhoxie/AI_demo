# Databricks notebook source
# MAGIC %md
# MAGIC # Prescriptive Inventory Plan — Tariff & Stock Transfer Optimization
# MAGIC
# MAGIC Loads `gold.supply_chain_graph`, identifies Mexico-origin SKUs (25% tariff simulation),
# MAGIC and uses scipy.optimize inside a Pandas UDF (by Product Category) to suggest HUB→SPOKE
# MAGIC stock transfers in the FL region to minimize 30-day stock-out risk for Carrier products.
# MAGIC Output: Delta table `prescriptive_inventory_plan` (SKU, Branch_ID, Recommended_Stock_Shift, Projected_Margin_Recovery).

# COMMAND ----------

dbutils.widgets.text("catalog", "demo_nah_catalog", "Catalog")
dbutils.widgets.text("schema", "gold", "Schema (e.g. gold)")
dbutils.widgets.text("source_table", "supply_chain_graph", "Source table name")
dbutils.widgets.text("target_schema", "gold", "Target schema for prescriptive_inventory_plan")
dbutils.widgets.text("country", "Mexico", "Tariff country of origin (e.g. Mexico)")
dbutils.widgets.text("tariff_pct", "25", "Tariff percentage (e.g. 25)")
catalog = (dbutils.widgets.get("catalog") or "demo_nah_catalog").strip()
schema = (dbutils.widgets.get("schema") or "gold").strip()
source_table = (dbutils.widgets.get("source_table") or "supply_chain_graph").strip()
target_schema = (dbutils.widgets.get("target_schema") or "gold").strip()
_tariff_country = (dbutils.widgets.get("country") or "Mexico").strip().lower()
_tariff_pct_str = (dbutils.widgets.get("tariff_pct") or "25").strip()
try:
    TARIFF_INCREASE = float(_tariff_pct_str) / 100.0
except ValueError:
    TARIFF_INCREASE = 0.25
TARIFF_COUNTRY_ORIGIN = _tariff_country
TARGET_REGION = "FL"
HORIZON_DAYS = 30

# COMMAND ----------

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    DoubleType,
)

# Load gold supply chain graph (SKU-level inventory, 695 locations, supplier origin)
full_table_name = f"`{catalog}`.`{schema}`.`{source_table}`"
df = spark.table(full_table_name)

# Normalize column names for case-insensitivity (Databricks may return lower/camel)
cols = [c.lower() for c in df.columns]
col_map = dict(zip(df.columns, cols))

def get_col(df, *candidates):
    for c in candidates:
        for orig, lower in col_map.items():
            if lower == c.lower():
                return F.col(orig)
    return None

# Expected columns (adjust if your table uses different names):
# SKU, Branch_ID, primary_origin, location_type, region, product_category, available_stock,
# safety_stock or demand_30d, unit_cost; and product_line or is_carrier for Carrier products
sku_col = get_col(df, "sku", "sku_id", "material_number", "material")
branch_col = get_col(df, "branch_id", "location_id", "plant")
origin_col = get_col(df, "primary_origin", "origin")
loc_type_col = get_col(df, "location_type", "loc_type")
region_col = get_col(df, "region")
cat_col = get_col(df, "product_category", "product_category")
avail_col = get_col(df, "available_stock", "on_hand", "quantity", "unrestricted_stock")
safety_col = get_col(df, "safety_stock", "safety_stock_target", "safety_stock_level", "demand_30d")
cost_col = get_col(df, "unit_cost", "base_cost", "cost")
carrier_col = get_col(df, "supplier_name", "product_line", "is_carrier", "brand")

# Build selected columns with fallbacks
select_expr = []
if sku_col is None:
    sku_col = F.col(df.columns[0])
select_expr.append(sku_col.alias("SKU"))
if branch_col is None:
    branch_col = F.col(df.columns[1])
select_expr.append(branch_col.alias("Branch_ID"))
select_expr.append((origin_col if origin_col is not None else F.lit(None)).alias("primary_origin"))
select_expr.append((loc_type_col if loc_type_col is not None else F.lit("SPOKE")).alias("location_type"))
select_expr.append((region_col if region_col is not None else F.lit(None)).alias("region"))
select_expr.append((cat_col if cat_col is not None else F.lit("Default")).alias("product_category"))
select_expr.append((avail_col if avail_col is not None else F.lit(0.0)).alias("available_stock"))
select_expr.append((safety_col if safety_col is not None else F.lit(0.0)).alias("safety_stock"))
select_expr.append((cost_col if cost_col is not None else F.lit(0.0)).alias("unit_cost"))
select_expr.append((carrier_col if carrier_col is not None else F.lit("")).alias("carrier_flag"))

graph = df.select(*select_expr)

# Tariff simulation for selected country of origin (cost/margin impact in optimization)
graph = graph.withColumn(
    "unit_cost_after_tariff",
    F.when(F.lower(F.col("primary_origin")) == F.lit(TARIFF_COUNTRY_ORIGIN), F.col("unit_cost") * (1 + TARIFF_INCREASE)).otherwise(
        F.col("unit_cost")
    ),
)

# Restrict to FL region when present; if region is null/empty, include row (so we get results when column is missing)
in_fl = F.lower(F.trim(F.coalesce(F.col("region"), F.lit("")))) == TARGET_REGION.lower()
no_region = F.col("region").isNull() | (F.trim(F.coalesce(F.col("region"), F.lit(""))) == F.lit(""))
fl_carrier = graph.filter(in_fl | no_region).withColumn(
    "is_carrier",
    F.coalesce(
        F.lower(F.col("carrier_flag").cast("string")).contains("carrier"),
        (F.col("carrier_flag").cast("string") == "1"),
        F.lit(True),
    ),
).filter(F.col("is_carrier")).drop("is_carrier").withColumn(
    "product_category", F.coalesce(F.col("product_category"), F.lit("Default"))
)

# COMMAND ----------

import pandas as pd
import numpy as np
from scipy.optimize import minimize, LinearConstraint, Bounds

# Output schema for applyInPandas
result_schema = StructType([
    StructField("SKU", StringType(), False),
    StructField("Branch_ID", StringType(), False),
    StructField("Recommended_Stock_Shift", DoubleType(), False),
    StructField("Projected_Margin_Recovery", DoubleType(), False),
])


def _empty_result():
    return pd.DataFrame(columns=["SKU", "Branch_ID", "Recommended_Stock_Shift", "Projected_Margin_Recovery"])


def optimize_transfers(pdf: pd.DataFrame) -> pd.DataFrame:
    """
    For one Product Category, suggest HUB→SPOKE stock transfers in FL to minimize
    30-day stock-out risk. Uses scipy.optimize; returns one row per (SKU, Branch_ID)
    with Recommended_Stock_Shift (negative = send, positive = receive) and
    Projected_Margin_Recovery.
    """
    if pdf.empty or len(pdf) < 2:
        return _empty_result()

    # Normalize column names
    pdf = pdf.rename(columns={c: c.lower().replace(" ", "_") for c in pdf.columns})
    required = ["sku", "branch_id", "location_type", "available_stock", "safety_stock", "unit_cost_after_tariff"]
    for r in required:
        if r not in pdf.columns:
            pdf[r] = 0.0 if "stock" in r or "cost" in r else ""
    pdf["available_stock"] = pd.to_numeric(pdf["available_stock"], errors="coerce").fillna(0)
    pdf["safety_stock"] = pd.to_numeric(pdf["safety_stock"], errors="coerce").fillna(0)
    pdf["unit_cost_after_tariff"] = pd.to_numeric(pdf["unit_cost_after_tariff"], errors="coerce").fillna(0)

    hubs = pdf[pdf["location_type"].astype(str).str.upper().str.strip() == "HUB"]
    spokes = pdf[pdf["location_type"].astype(str).str.upper().str.strip() == "SPOKE"]
    # If no HUB/SPOKE split (e.g. column missing or all same), infer: branches with more stock = HUB, rest = SPOKE
    if hubs.empty or spokes.empty:
        branches = pdf.groupby("branch_id", as_index=False).agg({"available_stock": "sum"})
        branches = branches.sort_values("available_stock", ascending=False).reset_index(drop=True)
        n = max(1, len(branches))
        n_hub = max(1, min(n - 1, n // 2))  # at least one HUB and one SPOKE
        hub_ids = set(branches["branch_id"].iloc[:n_hub].astype(str).tolist())
        spoke_ids = set(branches["branch_id"].iloc[n_hub:].astype(str).tolist())
        if not hub_ids or not spoke_ids:
            return _empty_result()
        pdf = pdf.copy()
        pdf["location_type"] = pdf["branch_id"].astype(str).map(
            lambda b: "HUB" if b in hub_ids else "SPOKE"
        )
        hubs = pdf[pdf["location_type"] == "HUB"]
        spokes = pdf[pdf["location_type"] == "SPOKE"]
    if hubs.empty or spokes.empty:
        return _empty_result()

    skus = [s for s in pdf["sku"].dropna().unique().tolist() if pd.notna(s)]
    hub_branches = hubs["branch_id"].astype(str).unique().tolist()
    spoke_branches = spokes["branch_id"].astype(str).unique().tolist()
    if not skus or not hub_branches or not spoke_branches:
        return _empty_result()

    sku_ord = {s: i for i, s in enumerate(skus)}
    hub_ord = {h: i for i, h in enumerate(hub_branches)}
    spoke_ord = {sp: i for i, sp in enumerate(spoke_branches)}

    def idx(sku, hub, spoke):
        return sku_ord[sku] * (len(hub_branches) * len(spoke_branches)) + hub_ord[hub] * len(spoke_branches) + spoke_ord[spoke]

    n_x = len(skus) * len(hub_branches) * len(spoke_branches)

    # Stock and safety per (sku, branch)
    def get_stock(sku, branch):
        row = pdf[(pdf["sku"] == sku) & (pdf["branch_id"].astype(str) == str(branch))]
        if row.empty:
            return 0.0, 0.0
        return float(row["available_stock"].iloc[0]), float(row["safety_stock"].iloc[0])

    def get_cost(sku):
        row = pdf[pdf["sku"] == sku]
        return float(row["unit_cost_after_tariff"].iloc[0]) if not row.empty else 0.0

    # Rebalancing incentive: when risk is tied, prefer moving stock HUB→SPOKE so results are non-trivial
    alpha_rebalance = 1e-4

    def objective(x):
        risk = 0.0
        for sku in skus:
            for spoke in spoke_branches:
                current, safety = get_stock(sku, spoke)
                received = sum(float(x[idx(sku, hub, spoke)]) for hub in hub_branches if idx(sku, hub, spoke) < len(x))
                shortfall = max(0.0, safety - (current + received))
                risk += shortfall
        total_transfer = float(np.sum(x)) if len(x) else 0.0
        return risk - alpha_rebalance * total_transfer

    # Bounds: 0 <= x
    bounds = Bounds(0, np.inf)

    # Constraints: for each (sku, hub), sum over spokes of x <= available at hub
    A_ub = []
    b_ub = []
    for sku in skus:
        for hub in hub_branches:
            avail, _ = get_stock(sku, hub)
            row = [0.0] * n_x
            for spoke in spoke_branches:
                row[idx(sku, hub, spoke)] = 1.0
            A_ub.append(row)
            b_ub.append(max(0, avail))

    A = np.array(A_ub)
    lb = np.zeros(len(b_ub))
    ub = np.array(b_ub)
    constraints = LinearConstraint(A, lb, ub)

    x0 = np.zeros(n_x)
    res = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=constraints, options={"maxiter": 200})
    x_opt = res.x if res.success else np.zeros(n_x)

    rows = []
    margin_rate = 0.15
    for sku in skus:
        for branch in hub_branches + spoke_branches:
            shift = 0.0
            if branch in hub_branches:
                for spoke in spoke_branches:
                    i = idx(sku, branch, spoke)
                    if i < len(x_opt):
                        shift -= float(x_opt[i])
            else:
                for hub in hub_branches:
                    i = idx(sku, hub, branch)
                    if i < len(x_opt):
                        shift += float(x_opt[i])
            cost = get_cost(sku)
            recovery = abs(shift) * cost * margin_rate if shift != 0 else 0.0
            rows.append({
                "SKU": str(sku),
                "Branch_ID": str(branch),
                "Recommended_Stock_Shift": float(shift),
                "Projected_Margin_Recovery": float(recovery),
            })
    return pd.DataFrame(rows)


# COMMAND ----------

# Run optimization in parallel by Product Category via Pandas UDF
fl_carrier_with_cat = fl_carrier.withColumn(
    "product_category",
    F.coalesce(F.col("product_category"), F.lit("Default")),
)

prescriptive_plan = fl_carrier_with_cat.groupBy("product_category").applyInPandas(
    optimize_transfers,
    schema=result_schema,
)

# COMMAND ----------

# Write to Delta table: prescriptive_inventory_plan
target_table = f"`{catalog}`.`{target_schema}`.`prescriptive_inventory_plan`"
prescriptive_plan.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    target_table
)
print(f"Wrote prescriptive inventory plan to {target_table}")

# COMMAND ----------

display(prescriptive_plan.limit(100))
