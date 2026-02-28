"""
Novelis Supply Chain & Production Dashboard — production-ready Flask app.
Four tabs: Overview, Supply Chain, Production OEE, Inventory & Logistics.
KPIs at top, bar charts below; Novelis-branded UI; data from gold tables.
"""
import logging
from flask import Flask, render_template, jsonify

from config import CATALOG, SCHEMA, databricks_configured
from data import (
    get_overview_kpis,
    get_supply_chain_data,
    get_production_oee_data,
    get_inventory_logistics_data,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/")
def index():
    return render_template(
        "index.html",
        catalog=CATALOG,
        schema=SCHEMA,
        databricks_connected=databricks_configured(),
    )


@app.route("/api/overview")
def api_overview():
    return jsonify(get_overview_kpis())


@app.route("/api/supply-chain")
def api_supply_chain():
    return jsonify(get_supply_chain_data())


@app.route("/api/production-oee")
def api_production_oee():
    return jsonify(get_production_oee_data())


@app.route("/api/inventory-logistics")
def api_inventory_logistics():
    return jsonify(get_inventory_logistics_data())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(__import__("os").environ.get("PORT", 5000)), debug=False)
