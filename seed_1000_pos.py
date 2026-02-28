#!/usr/bin/env python3
"""
Seed the Supply Chain Control Tower database with 1000 purchase orders
from multiple countries. Requires PG* env vars (or Databricks OAuth).

Usage:
  python seed_1000_pos.py           # seed 1000 POs (replaces existing procurement)
  python seed_1000_pos.py -n 500   # seed 500 POs
  python seed_1000_pos.py -s 123   # different random seed
"""
import argparse
import sys

import db
from build_sap_data import build_sap_data


def main():
    parser = argparse.ArgumentParser(description="Seed control tower with multi-country purchase orders.")
    parser.add_argument("-n", "--count", type=int, default=1000, help="Number of POs to generate (default 1000)")
    parser.add_argument("-s", "--seed", type=int, default=42, help="Random seed (default 42)")
    args = parser.parse_args()

    if not db.init_supply_chain_tables():
        print("DB init failed. Set PGDATABASE, PGUSER, PGHOST, PGPORT, PGPASSWORD (or use Databricks OAuth).", file=sys.stderr)
        sys.exit(1)

    data = build_sap_data(n_per_domain=12, n_procurement=args.count, seed=args.seed)
    procurement = data["procurement"]
    if not db.seed_procurement_only(procurement):
        sys.exit(1)
    print(f"Seeded {len(procurement)} purchase orders from {len(set(p.get('country') for p in procurement if p.get('country')))} countries.")


if __name__ == "__main__":
    main()
