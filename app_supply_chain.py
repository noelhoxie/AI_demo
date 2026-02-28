"""
Supply Chain Control Tower — served with data from PostgreSQL.

Uses the same connection pattern as your Dash app:
  - Env: PGDATABASE, PGUSER, PGHOST, PGPORT, PGSSLMODE, PGAPPNAME (and PGPASSWORD or OAuth in Databricks)
  - Connection pool + OAuth token refresh via db.py

Run:
  Set PG* env vars (or use Databricks OAuth), then:
  python app_supply_chain.py

  Open http://127.0.0.1:8050/ (or the URL shown).
"""
import json
import os
from pathlib import Path

from flask import Flask, Response, request, jsonify

import db
from data_pipeline.build_sap_data import build_sap_data
from supply_chain_simulator import run_simulation
from tariff_rates import enrich_procurement_with_tariff

app = Flask(__name__)

# Path to the control tower HTML (same directory as this script)
HTML_PATH = Path(__file__).resolve().parent / "supply_chain_control_tower.html"


def ensure_data_seeded():
    """If any supply chain table is empty, seed from build_sap_data."""
    data = db.get_sap_data()
    if not data["procurement"] and not data["inventory"]:
        sap_dict = build_sap_data(n_per_domain=12, seed=42)
        db.seed_sap_data(sap_dict)
        print("Seeded supply chain tables from build_sap_data().")


@app.route("/")
def index():
    """Serve the control tower HTML with SAP data from PostgreSQL injected."""
    if not HTML_PATH.exists():
        return f"Control tower HTML not found: {HTML_PATH}", 404

    html_content = HTML_PATH.read_text(encoding="utf-8")

    try:
        sap_data = db.get_sap_data()
        sap_data["procurement"] = enrich_procurement_with_tariff(sap_data["procurement"])
    except Exception as e:
        sap_data = {
            "procurement": [],
            "inventory": [],
            "manufacturing": [],
            "logistics": [],
            "demand": [],
        }
        print(f"DB fetch failed, serving empty data: {e}")

    # Inject data so the front-end calls window.loadSAPData(...) on load
    script = f"<script>window.loadSAPData({json.dumps(sap_data)});</script>"
    # Insert before </body>
    if "</body>" in html_content:
        html_content = html_content.replace("</body>", script + "\n</body>")
    else:
        html_content = html_content + script

    return Response(html_content, mimetype="text/html; charset=utf-8")


@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    """
    Run disruption simulation. Expects JSON body:
    { "disruptions": [ { "type": str, "severity": "low"|"medium"|"high", "scope": str|null } ], "seed": int|null }
    Returns { "sap": { procurement, inventory, manufacturing, logistics, demand } }.
    """
    try:
        payload = request.get_json(force=True, silent=True) or {}
        disruptions = payload.get("disruptions") or []
        seed = payload.get("seed")

        sap_data = db.get_sap_data()
        if not sap_data.get("procurement") and not sap_data.get("inventory"):
            sap_dict = build_sap_data(n_per_domain=12, seed=42)
            db.seed_sap_data(sap_dict)
            sap_data = db.get_sap_data()

        result = run_simulation(sap_data, disruptions, seed=seed)
        result["procurement"] = enrich_procurement_with_tariff(result["procurement"])
        return jsonify({"sap": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


def main():
    if not db.init_supply_chain_tables():
        print("Warning: DB init failed. Set PGDATABASE, PGUSER, PGHOST, PGPORT, and PGPASSWORD (or use Databricks OAuth).")
    else:
        ensure_data_seeded()

    port = int(os.getenv("PORT", "8050"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")


if __name__ == "__main__":
    main()
