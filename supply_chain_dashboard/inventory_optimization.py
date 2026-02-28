"""
Inventory optimization model: financial impact of reducing days of supply from 14 to lower targets.
Uses current inventory KPIs and by-plant data; derives inventory value from quantity
and average unit cost, then computes target levels and savings. Includes scenario analysis
for multiple target days (10, 7, 5).
"""
from typing import Any, Dict, List

from data import get_inventory_kpis, get_inventory_charts

# Assumed average unit value (COGS or replacement cost) when not in source data
DEFAULT_AVG_UNIT_VALUE = 52.0
# Annual holding cost as fraction of inventory value (capital, storage, insurance, obsolescence)
ANNUAL_HOLDING_COST_PCT = 0.24
# Current days of supply (baseline)
CURRENT_DAYS_SUPPLY = 14
# Primary target for summary (kept for backward compatibility)
TARGET_DAYS_SUPPLY = 7
# Scenario analysis: multiple target days to compare
SCENARIO_TARGET_DAYS = [10, 7, 5]


def get_inventory_optimization() -> Dict[str, Any]:
    """
    Compare 14-day baseline to multiple target scenarios. Returns:
    - summary: current/primary target (7d) values, reduction, working capital freed, annual holding savings
    - scenarios: list of { target_days, target_value, reduction, working_capital_freed, annual_holding_savings } for 10d, 7d, 5d
    - by_plant: per-plant current/target value and reduction (for primary 7d target)
    - assumptions: avg_unit_value, holding_cost_pct
    """
    kpis = get_inventory_kpis()
    charts = get_inventory_charts()
    by_plant = charts.get("inventory_by_plant") or []

    total_qty = float(kpis.get("total_unrestricted_qty") or 0)
    avg_unit_value = float(kpis.get("avg_unit_value") or DEFAULT_AVG_UNIT_VALUE)

    current_inventory_value = total_qty * avg_unit_value
    ratio_primary = TARGET_DAYS_SUPPLY / CURRENT_DAYS_SUPPLY
    target_inventory_value = current_inventory_value * ratio_primary
    inventory_reduction_value = current_inventory_value - target_inventory_value
    annual_holding_savings = inventory_reduction_value * ANNUAL_HOLDING_COST_PCT

    daily_consumption_value = current_inventory_value / CURRENT_DAYS_SUPPLY if CURRENT_DAYS_SUPPLY else 0

    # Scenario analysis: one row per target days
    scenarios: List[Dict[str, Any]] = []
    for target_days in SCENARIO_TARGET_DAYS:
        if target_days >= CURRENT_DAYS_SUPPLY:
            continue
        r = target_days / CURRENT_DAYS_SUPPLY
        tgt_val = current_inventory_value * r
        reduction = current_inventory_value - tgt_val
        scenarios.append({
            "target_days": target_days,
            "target_inventory_value": round(tgt_val, 2),
            "inventory_reduction_value": round(reduction, 2),
            "working_capital_freed": round(reduction, 2),
            "annual_holding_cost_savings": round(reduction * ANNUAL_HOLDING_COST_PCT, 2),
        })

    by_plant_result: List[Dict[str, Any]] = []
    for row in by_plant:
        plant = row.get("plant") or ""
        qty = float(row.get("quantity") or 0)
        current_val = qty * avg_unit_value
        target_val = current_val * ratio_primary
        reduction = current_val - target_val
        by_plant_result.append({
            "plant": plant,
            "current_quantity": qty,
            "target_quantity": round(qty * ratio_primary, 0),
            "current_value": round(current_val, 2),
            "target_value": round(target_val, 2),
            "reduction_value": round(reduction, 2),
        })

    return {
        "summary": {
            "current_days_of_supply": CURRENT_DAYS_SUPPLY,
            "target_days_of_supply": TARGET_DAYS_SUPPLY,
            "current_inventory_value": round(current_inventory_value, 2),
            "target_inventory_value": round(target_inventory_value, 2),
            "inventory_reduction_value": round(inventory_reduction_value, 2),
            "working_capital_freed": round(inventory_reduction_value, 2),
            "annual_holding_cost_savings": round(annual_holding_savings, 2),
            "daily_consumption_value": round(daily_consumption_value, 2),
            "total_unrestricted_qty": total_qty,
        },
        "scenarios": scenarios,
        "by_plant": by_plant_result,
        "assumptions": {
            "avg_unit_value": avg_unit_value,
            "annual_holding_cost_pct": ANNUAL_HOLDING_COST_PCT,
        },
    }
