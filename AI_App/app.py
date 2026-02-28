"""
Supply Chain Dashboard — SAP + QAD gold data, Postgres comments.
Four tabs: Orders, Procurement, Inventory & Delivery, Production OEE.
Clean UI (no icons); KPIs at top; comments stored in Databricks Postgres.
"""
import logging
from flask import Flask, render_template, jsonify, request

from config import CATALOG, SCHEMA, databricks_configured, postgres_configured
from data import (
    get_orders_kpis,
    get_orders_charts,
    get_procurement_kpis,
    get_procurement_charts,
    get_inventory_kpis,
    get_inventory_charts,
    get_delivery_kpis,
    get_delivery_charts,
    get_production_kpis,
    get_production_charts,
)
from comments import init_comments_table, get_comments, add_comment
from company import get_company

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

# Ensure comments table exists when Postgres is configured
if postgres_configured():
    try:
        init_comments_table()
    except Exception as e:
        log.warning("Could not init comments table at startup: %s", e)

app = Flask(__name__)


@app.context_processor
def inject_company():
    """Make company branding available in every template."""
    return {"company": get_company()}


@app.route("/")
def index():
    return render_template(
        "index.html",
        catalog=CATALOG,
        schema=SCHEMA,
        databricks_connected=databricks_configured(),
        postgres_connected=postgres_configured(),
    )


@app.route("/actions")
def actions_page():
    return render_template("actions.html")


@app.route("/api/orders")
def api_orders():
    return jsonify({
        "kpis": get_orders_kpis(),
        **get_orders_charts(),
    })


@app.route("/api/procurement")
def api_procurement():
    return jsonify({
        "kpis": get_procurement_kpis(),
        **get_procurement_charts(),
    })


@app.route("/api/inventory-delivery")
def api_inventory_delivery():
    return jsonify({
        "inventory_kpis": get_inventory_kpis(),
        "delivery_kpis": get_delivery_kpis(),
        **get_inventory_charts(),
        **get_delivery_charts(),
    })


@app.route("/api/production")
def api_production():
    return jsonify({
        "kpis": get_production_kpis(),
        **get_production_charts(),
    })


@app.route("/api/comments", methods=["GET"])
def api_comments_list():
    tab = request.args.get("tab")
    return jsonify(get_comments(tab=tab))


@app.route("/api/comments", methods=["POST"])
def api_comments_post():
    data = request.get_json() or {}
    tab = data.get("tab", "").strip()
    content = data.get("content", "").strip()
    if not tab or not content:
        return jsonify({"error": "tab and content required"}), 400
    comment = add_comment(tab=tab, content=content)
    if comment is None:
        return jsonify({"error": "Failed to save comment"}), 500
    return jsonify(comment), 201


@app.route("/api/init-db")
def api_init_db():
    """Create Postgres schema and dashboard_comments table if missing."""
    if not postgres_configured():
        return jsonify({"ok": False, "error": "Postgres not configured"}), 503
    ok = init_comments_table()
    return jsonify({"ok": ok})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(__import__("os").environ.get("PORT", 5000)), debug=False)
