"""
Generate 1000 fake customer orders for delivery to 20 US locations.
Each order is fulfilled from one of several US manufacturing locations (origin).
All orders are due for delivery in the next 7 days from "today" (or as_of date).
Run: python generate_fake_orders.py
Output: fake_orders.json (and fake_orders.csv) in this directory.
"""
import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

# US manufacturing locations (origin): site_id, name, city, state, zip_prefix
MANUFACTURING_LOCATIONS = [
    ("MFG-01", "Midwest Plant", "Chicago", "IL", "606"),
    ("MFG-02", "South Central DC", "Dallas", "TX", "752"),
    ("MFG-03", "Northeast Plant", "Philadelphia", "PA", "191"),
    ("MFG-04", "Southeast Plant", "Atlanta", "GA", "303"),
    ("MFG-05", "West Coast DC", "Los Angeles", "CA", "900"),
    ("MFG-06", "Great Lakes Plant", "Detroit", "MI", "482"),
    ("MFG-07", "Southwest Plant", "Phoenix", "AZ", "850"),
    ("MFG-08", "Pacific Northwest DC", "Seattle", "WA", "981"),
]

# 20 US delivery locations (city, state, zip prefix for realism)
DELIVERY_LOCATIONS = [
    ("New York", "NY", "100"),
    ("Los Angeles", "CA", "900"),
    ("Chicago", "IL", "606"),
    ("Houston", "TX", "770"),
    ("Phoenix", "AZ", "850"),
    ("Philadelphia", "PA", "191"),
    ("San Antonio", "TX", "782"),
    ("San Diego", "CA", "921"),
    ("Dallas", "TX", "752"),
    ("San Jose", "CA", "951"),
    ("Austin", "TX", "787"),
    ("Jacksonville", "FL", "322"),
    ("Fort Worth", "TX", "761"),
    ("Columbus", "OH", "432"),
    ("Charlotte", "NC", "282"),
    ("Seattle", "WA", "981"),
    ("Denver", "CO", "802"),
    ("Boston", "MA", "021"),
    ("Nashville", "TN", "372"),
    ("Detroit", "MI", "482"),
]

# Fake company / recipient name stems (mixed B2B-style and generic)
COMPANY_STEMS = [
    "Acme", "Summit", "Premier", "Global", "Pacific", "Metro", "Central",
    "United", "National", "First", "Prime", "Elite", "Apex", "Vertex",
    "Pioneer", "Horizon", "Sterling", "Crown", "Atlas", "Fusion",
]
SUFFIXES = ["Inc", "LLC", "Corp", "Co", "Group", "Solutions", "Services", "Supply", "Distribution", ""]

# Product line names for item_count and value realism
LINES = ["Parts", "Materials", "Equipment", "Supplies", "Components", "Goods"]

# Order statuses
STATUSES = ["open", "confirmed", "picked", "shipped", "delivered"]
# Weights so most orders are shipped/delivered, some open/confirmed
STATUS_WEIGHTS = [0.08, 0.07, 0.10, 0.25, 0.50]

def random_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))

def generate_orders(
    n: int = 1000,
    seed: Optional[int] = 42,
    as_of: Optional[datetime] = None,
) -> List[dict]:
    """Generate orders all due for delivery in the next 7 days from as_of (default: today)."""
    if seed is not None:
        random.seed(seed)
    today = (as_of or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    next_week_end = today + timedelta(days=6)  # today through today+6 = 7 days
    order_start = today - timedelta(days=14)   # orders placed up to 14 days ago
    order_end = today - timedelta(days=1)     # up to yesterday
    orders = []
    for i in range(1, n + 1):
        # Origin: one of the US manufacturing locations
        origin_site_id, origin_name, origin_city, origin_state, origin_zip_prefix = random.choice(MANUFACTURING_LOCATIONS)
        origin_zip = origin_zip_prefix + str(random.randint(10, 99))
        # Destination: one of the 20 delivery locations
        city, state, zip_prefix = random.choice(DELIVERY_LOCATIONS)
        delivery_zip = zip_prefix + str(random.randint(10, 99))
        street_num = random.randint(1, 9999)
        street = random.choice(["Main St", "Oak Ave", "Industrial Blvd", "Commerce Dr", "Parkway", "Highway 10", "Warehouse Rd"])
        delivery_due = random_date(today, next_week_end)
        order_date = random_date(order_start, order_end)
        item_count = random.randint(1, 24)
        total_usd = round(random.uniform(150, 25000), 2)
        status = random.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]
        company = random.choice(COMPANY_STEMS) + " " + (random.choice(SUFFIXES) or random.choice(LINES))
        company = company.strip()
        orders.append({
            "order_id": f"ORD-{10000 + i}",
            "origin_site_id": origin_site_id,
            "origin_name": origin_name,
            "origin_city": origin_city,
            "origin_state": origin_state,
            "origin_zip": origin_zip,
            "customer_name": company,
            "delivery_city": city,
            "delivery_state": state,
            "delivery_zip": delivery_zip,
            "delivery_address": f"{street_num} {street}",
            "order_date": order_date.strftime("%Y-%m-%d"),
            "delivery_due_date": delivery_due.strftime("%Y-%m-%d"),
            "total_usd": total_usd,
            "item_count": item_count,
            "status": status,
        })
    return orders

def main():
    script_dir = Path(__file__).resolve().parent
    orders = generate_orders(1000)
    out_json = script_dir / "fake_orders.json"
    out_csv = script_dir / "fake_orders.csv"
    with open(out_json, "w") as f:
        json.dump(orders, f, indent=2)
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=orders[0].keys())
        w.writeheader()
        w.writerows(orders)
    print(f"Wrote {len(orders)} orders to {out_json} and {out_csv}")
    due_dates = sorted(set(o["delivery_due_date"] for o in orders))
    print(f"All delivery_due_date in next 7 days: {due_dates[0]} .. {due_dates[-1]}")
    by_city = {}
    for o in orders:
        k = (o["delivery_city"], o["delivery_state"])
        by_city[k] = by_city.get(k, 0) + 1
    print("Orders per delivery location (city, state):", dict(sorted(by_city.items(), key=lambda x: -x[1])))
    by_origin = {}
    for o in orders:
        k = o["origin_site_id"]
        by_origin[k] = by_origin.get(k, 0) + 1
    print("Orders per manufacturing origin:", dict(sorted(by_origin.items())))

if __name__ == "__main__":
    main()
