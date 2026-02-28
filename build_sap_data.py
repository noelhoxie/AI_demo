#!/usr/bin/env python3
"""
Generate SAP-style supply chain data for the Supply Chain Control Tower.
Output matches the structure expected by supply_chain_control_tower.html (window.loadSAPData).

Usage:
  python build_sap_data.py                    # print JSON to stdout
  python build_sap_data.py -o sap_data.json   # write to file
  python build_sap_data.py -n 20              # more records per domain

In Databricks, import and pass result to displayHTML:
  from build_sap_data import build_sap_data
  data = build_sap_data(n_per_domain=15)
  html = open('supply_chain_control_tower.html').read() + "<script>window.loadSAPData(" + json.dumps(data) + ");</script>"
  displayHTML(html)
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


# Master data for consistent references across domains
VENDORS = [
    ("V-10001", "Global Parts Inc."),
    ("V-10002", "Steel Works Ltd."),
    ("V-10003", "Chem Supply Co."),
    ("V-10004", "Packaging Pro"),
    ("V-10005", "Electronics Supply"),
    ("V-10006", "Raw Materials Corp."),
]

# Countries and vendor names for multi-country purchase orders (1000 POs)
COUNTRIES = [
    "Germany", "China", "Mexico", "Japan", "Canada", "South Korea", "Vietnam", "India",
    "Italy", "France", "United Kingdom", "Spain", "Netherlands", "Poland", "Taiwan",
    "Thailand", "Malaysia", "Indonesia", "Brazil", "Turkey", "Czech Republic", "Hungary",
    "Belgium", "Austria", "Switzerland", "Sweden", "Israel", "Ireland", "Portugal",
    "Romania", "Slovakia", "Australia", "South Africa", "Argentina", "Chile", "Colombia",
]
VENDOR_NAMES_BY_TYPE = [
    "Steel & Metals", "Chemicals & Plastics", "Electronics", "Packaging", "Raw Materials",
    "Precision Parts", "Industrial Supply", "Components Inc", "Materials Corp", "Global Sourcing",
]
PLANTS = ["1000", "2000", "3000"]
STORAGE_LOCATIONS = ["0001", "0002", "0003"]
RAW_MATERIALS = [f"MAT-80{i:02d}" for i in range(1, 12)]
FINISHED_GOODS = [f"FG-90{i:02d}" for i in range(1, 8)]
CUSTOMERS = [f"CUST-{c}{i:03d}" for c in "ABCD" for i in range(1, 6)]
CARRIERS = ["DHL", "FedEx", "UPS", "Maersk", "XPO Logistics"]
PO_STATUSES = ["Open", "Confirmed", "Delivered", "Overdue"]
MFG_STATUSES = ["Released", "Confirmed", "Completed", "Cancelled"]
LOGISTICS_STATUSES = ["Pending", "In Transit", "Delivered"]
DEMAND_STATUSES = ["Open", "Confirmed", "Delivered"]


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def build_procurement(n: int, base_date: datetime) -> List[dict]:
    """Build n purchase orders. Uses multi-country vendors when n > 50."""
    out = []
    use_multi_country = n > 50
    seen_pos = set()
    for i in range(n):
        if use_multi_country:
            country = random.choice(COUNTRIES)
            vname = random.choice(VENDOR_NAMES_BY_TYPE) + " (" + country + ")"
            vid = f"V-{country[:2].upper()}{random.randint(1000, 9999)}"
        else:
            vid, vname = random.choice(VENDORS)
            country = ""
        material = random.choice(RAW_MATERIALS)
        qty = random.randint(50, 2000)
        value = round(qty * random.uniform(5, 50), 2)
        status = random.choice(PO_STATUSES)
        days = random.randint(-5, 30)
        delivery = base_date + timedelta(days=days)
        if status == "Overdue":
            delivery = base_date - timedelta(days=random.randint(1, 10))
        po_num = f"45{random.randint(10000000, 99999999)}"
        while po_num in seen_pos:
            po_num = f"45{random.randint(10000000, 99999999)}"
        seen_pos.add(po_num)
        rec = {
            "po": po_num,
            "vendor": vid,
            "vendorName": vname,
            "material": material,
            "qty": qty,
            "value": value,
            "status": status,
            "delivery": _date_str(delivery),
        }
        if use_multi_country:
            rec["country"] = country
        else:
            rec["country"] = ""
        out.append(rec)
    return out


def build_inventory(n: int) -> List[dict]:
    out = []
    seen = set()
    materials = RAW_MATERIALS + FINISHED_GOODS
    for _ in range(n):
        material = random.choice(materials)
        plant = random.choice(PLANTS)
        sloc = random.choice(STORAGE_LOCATIONS)
        key = (material, plant, sloc)
        if key in seen:
            continue
        seen.add(key)
        unrestricted = random.randint(0, 15000)
        blocked = random.randint(0, 100) if random.random() < 0.3 else 0
        in_transit = random.randint(0, 1500) if random.random() < 0.5 else 0
        reorder_point = random.randint(200, 2000)
        out.append({
            "material": material,
            "plant": plant,
            "storageLoc": sloc,
            "unrestricted": unrestricted,
            "blocked": blocked,
            "inTransit": in_transit,
            "reorderPoint": reorder_point,
        })
    return out


def build_manufacturing(n: int, base_date: datetime) -> List[dict]:
    out = []
    for i in range(n):
        material = random.choice(FINISHED_GOODS)
        plant = random.choice(PLANTS)
        qty = random.choice([500, 750, 1000, 1500, 2000])
        status = random.choice(MFG_STATUSES)
        start = base_date + timedelta(days=random.randint(-15, 5))
        end = start + timedelta(days=random.randint(3, 14))
        out.append({
            "order": str(1000000 + i + 1),
            "material": material,
            "plant": plant,
            "qty": qty,
            "status": status,
            "start": _date_str(start),
            "end": _date_str(end),
        })
    return out


def build_logistics(n: int, base_date: datetime) -> List[dict]:
    out = []
    materials = FINISHED_GOODS + RAW_MATERIALS[:3]
    for i in range(n):
        ship_to = random.choice(CUSTOMERS)
        material = random.choice(materials)
        qty = random.randint(50, 500)
        status = random.choice(LOGISTICS_STATUSES)
        planned = base_date + timedelta(days=random.randint(-2, 14))
        out.append({
            "delivery": f"80{random.randint(10000000, 99999999)}",
            "shipTo": ship_to,
            "material": material,
            "qty": qty,
            "status": status,
            "planned": _date_str(planned),
            "carrier": random.choice(CARRIERS),
        })
    return out


def build_demand(n: int, base_date: datetime) -> List[dict]:
    out = []
    for i in range(n):
        customer = random.choice(CUSTOMERS)
        material = random.choice(FINISHED_GOODS)
        qty = random.randint(50, 600)
        forecast_qty = qty + random.randint(-30, 50)
        status = random.choice(DEMAND_STATUSES)
        request_date = base_date + timedelta(days=random.randint(0, 45))
        out.append({
            "order": str(100000 + i + 1),
            "customer": customer,
            "material": material,
            "qty": qty,
            "requestDate": _date_str(request_date),
            "status": status,
            "forecastQty": max(0, forecast_qty),
        })
    return out


def build_sap_data(
    n_per_domain: int = 10,
    base_date: Optional[datetime] = None,
    seed: Optional[int] = None,
    n_procurement: Optional[int] = None,
) -> Dict[str, List[dict]]:
    """
    Build a full SAP-style dataset for the control tower.

    Args:
        n_per_domain: Approximate number of records per domain (inventory may be less due to dedup).
        base_date: Reference date for delivery/start/planned dates; defaults to today.
        seed: Random seed for reproducibility.
        n_procurement: If set, generate this many purchase orders (from multiple countries); overrides n_per_domain for procurement only.

    Returns:
        Dict with keys: procurement, inventory, manufacturing, logistics, demand.
    """
    if seed is not None:
        random.seed(seed)
    base = base_date or datetime.now()
    n_po = n_procurement if n_procurement is not None else n_per_domain

    return {
        "procurement": build_procurement(n_po, base),
        "inventory": build_inventory(min(n_per_domain * 2, 50)),
        "manufacturing": build_manufacturing(n_per_domain, base),
        "logistics": build_logistics(n_per_domain, base),
        "demand": build_demand(n_per_domain, base),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate SAP-style supply chain data for the Control Tower.")
    parser.add_argument("-n", "--count", type=int, default=12, help="Records per domain (default 12)")
    parser.add_argument("-p", "--procurement", type=int, default=None, metavar="N", help="Generate N purchase orders from multiple countries (e.g. 1000)")
    parser.add_argument("-o", "--output", type=str, help="Output JSON file path")
    parser.add_argument("-s", "--seed", type=int, default=42, help="Random seed (default 42)")
    args = parser.parse_args()

    data = build_sap_data(
        n_per_domain=args.count,
        seed=args.seed,
        n_procurement=args.procurement,
    )
    json_str = json.dumps(data, indent=2)

    if args.output:
        Path(args.output).write_text(json_str, encoding="utf-8")
        print(f"Wrote {len(json_str)} bytes to {args.output}", file=__import__("sys").stderr)
    else:
        print(json_str)


if __name__ == "__main__":
    main()
