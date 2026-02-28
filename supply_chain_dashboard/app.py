"""
Supply Chain Dashboard — SAP + QAD gold data, Postgres comments.
Four tabs: Orders, Procurement, Inventory & Delivery, Production.
Clean UI (no icons); KPIs at top; comments stored in Databricks Postgres.
"""
import logging
from flask import Flask, render_template, jsonify, request, redirect, url_for

from config import databricks_configured, postgres_configured, FRED_API_KEY
from data import (
    get_orders_kpis,
    get_orders_charts,
    get_procurement_kpis,
    get_procurement_charts,
    get_supplier_scorecard,
    get_supplier_scorecard_detail,
    get_outstanding_pos,
    add_purchase_order,
    update_purchase_order,
    get_production_kpis,
    get_production_charts,
    get_production_oee_forecast_7d,
    get_production_orders,
    update_production_order,
    get_inventory_optimization_kpis,
    get_inventory_optimization_charts,
)
from comments import init_comments_table, get_comments, add_comment
from company import get_company
from simulator import run_dashboard_simulation
from tariffs import get_tariffs
from weather_delays import get_weather_delays
from weather_by_zip import get_weather_by_zip
from orders_weather import (
    get_orders_with_weather,
    get_orders_by_state,
    get_orders_by_zip,
    get_delivery_locations,
    get_origin_destination_routes,
)
from reroute import get_orders_weather_alerts_with_reroute
from reassignments_store import (
    add as reassignment_add,
    get_all as reassignments_get_all,
    get_by_id as reassignment_get_by_id,
    set_status as reassignment_set_status,
    send_approval_email,
    mark_email_sent,
)

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


# Tiered nav: which parent section each page belongs to, and subpages per parent.
NAV_SECTION_TO_PARENT = {
    "procurement": "procurement",
    "tariffs": "procurement",
    "purchase-orders": "procurement",
    "supplier-scorecard": "procurement",
    "production": "production",
    "production-orders": "production",
    "production-targets": "production",
    "forecasting": "demand",
    "demand-dashboard": "demand",
    "sales-orders": "demand",
    "supply-overview": "supply",
    "inventory-optimization": "supply",
    "weather-delays": "supply",
    "alerts": "supply",
}
NAV_TIERS = {
    "procurement": [
        ("procurement_page", "Overview", "procurement"),
        ("tariffs_page", "Tariffs", "tariffs"),
        ("purchase_orders_page", "Outstanding POs", "purchase-orders"),
        ("procurement_page", "Supplier scorecard", "supplier-scorecard"),
    ],
    "production": [
        ("production_page", "Overview", "production"),
        ("production_orders_page", "Production orders", "production-orders"),
        ("production_targets_page", "Targets & downtime", "production-targets"),
    ],
    "demand": [
        ("demand_dashboard_page", "Dashboard", "demand-dashboard"),
        ("forecasting_page", "Forecasting", "forecasting"),
        ("sales_orders_page", "Sales orders", "sales-orders"),
    ],
    "supply": [
        ("supply_overview_page", "Overview", "supply-overview"),
        ("weather_delays_page", "Weather map", "weather-delays"),
        ("alerts_page", "Weather alerts", "alerts"),
    ],
}


@app.context_processor
def inject_company():
    """Make company branding available in every template."""
    return {"company": get_company()}


@app.context_processor
def inject_nav_tiers():
    """Tiered nav: subpages per parent section (for sub-nav row)."""
    return {
        "nav_section_to_parent": NAV_SECTION_TO_PARENT,
        "nav_tiers": NAV_TIERS,
    }


def _dashboard_context():
    return {
        "databricks_connected": databricks_configured(),
        "postgres_connected": postgres_configured(),
    }


@app.route("/")
def index():
    return redirect(url_for("procurement_page"))


@app.route("/orders")
def orders_page():
    return redirect(url_for("procurement_page"))


@app.route("/procurement")
def procurement_page():
    return render_template(
        "procurement.html",
        section="procurement",
        section_title="Procurement",
        **_dashboard_context(),
    )


@app.route("/production")
def production_page():
    return render_template(
        "production.html",
        section="production",
        section_title="Production",
        **_dashboard_context(),
    )


@app.route("/simulator")
def simulator_page():
    return render_template(
        "simulator.html",
        section="simulator",
        section_title="Simulator",
        **_dashboard_context(),
    )


@app.route("/production-orders")
def production_orders_page():
    """Redirect to Production page with Production orders panel visible (hash)."""
    return redirect(url_for("production_page") + "#production-orders")


@app.route("/production-targets")
def production_targets_page():
    """Redirect to Production page with Targets & downtime panel visible (hash)."""
    return redirect(url_for("production_page") + "#production-targets")


@app.route("/tariffs")
def tariffs_page():
    """Redirect to Procurement page with Tariffs panel visible (hash)."""
    return redirect(url_for("procurement_page") + "#tariffs")


@app.route("/purchase-orders")
def purchase_orders_page():
    """Redirect to Procurement page with Outstanding POs panel visible (hash)."""
    return redirect(url_for("procurement_page") + "#purchase-orders")


@app.route("/supplier-scorecard")
def supplier_scorecard_page():
    """Redirect to Procurement page with Supplier scorecard panel visible (hash)."""
    return redirect(url_for("procurement_page") + "#supplier-scorecard")


@app.route("/demand")
def demand_dashboard_page():
    """Demand dashboard: KPIs and charts (orders as demand proxy)."""
    return render_template(
        "demand_dashboard.html",
        section="demand-dashboard",
        section_title="Demand",
        **_dashboard_context(),
    )


@app.route("/forecasting")
def forecasting_page():
    """Redirect to Demand page with Forecasting panel visible (hash)."""
    return redirect(url_for("demand_dashboard_page") + "#forecasting")


@app.route("/sales-orders")
def sales_orders_page():
    """Redirect to Demand page with Sales orders panel visible (hash)."""
    return redirect(url_for("demand_dashboard_page") + "#sales-orders")


@app.route("/supply")
def supply_overview_page():
    """Supply overview: inventory and supply KPIs (production-style summary)."""
    return render_template(
        "supply_overview.html",
        section="supply-overview",
        section_title="Supply",
        **_dashboard_context(),
    )


@app.route("/inventory-optimization")
def inventory_optimization_page():
    return render_template(
        "inventory_optimization.html",
        section="inventory-optimization",
        section_title="Inventory optimization",
        **_dashboard_context(),
    )


@app.route("/executive-summary")
def executive_summary_page():
    return render_template(
        "executive_summary.html",
        section="executive-summary",
        section_title="Executive Summary",
        **_dashboard_context(),
    )


@app.route("/actions")
def actions_page():
    return render_template("actions.html")


@app.route("/weather-delays")
def weather_delays_page():
    """Redirect to Supply page with Weather map panel visible (hash)."""
    return redirect(url_for("supply_overview_page") + "#weather-delays")


@app.route("/api/weather-delays")
def api_weather_delays():
    return jsonify(get_weather_delays())


@app.route("/alerts")
def alerts_page():
    """Redirect to Supply page with Weather alerts panel visible (hash)."""
    return redirect(url_for("supply_overview_page") + "#alerts")


@app.route("/api/orders-with-weather")
def api_orders_with_weather():
    """Orders (fake_orders.json) enriched with weather delay by origin/destination state."""
    return jsonify(get_orders_with_weather())


@app.route("/api/orders-by-state")
def api_orders_by_state():
    """Orders grouped by delivery state (for weather map drill-down)."""
    return jsonify(get_orders_by_state())


@app.route("/api/delivery-locations")
def api_delivery_locations():
    """Delivery locations with lat/lon and order counts for map point markers."""
    return jsonify(get_delivery_locations())


@app.route("/api/origin-destination-routes")
def api_origin_destination_routes():
    """Origin-to-destination routes with coordinates for map lines (one per unique origin–delivery pair)."""
    return jsonify(get_origin_destination_routes())


@app.route("/api/orders-by-zip")
def api_orders_by_zip():
    """Orders grouped by delivery zip (for weather map zip drill-down)."""
    return jsonify(get_orders_by_zip())


@app.route("/api/weather-by-zip")
def api_weather_by_zip():
    """Weather conditions (delay) by zip-level grid for granular map."""
    from weather_by_zip import get_weather_by_zip
    return jsonify(get_weather_by_zip())


@app.route("/api/orders-weather-alerts")
def api_orders_weather_alerts():
    """At-risk orders with reroute suggestion and capacity impact on suggested plant."""
    return jsonify(get_orders_weather_alerts_with_reroute())


@app.route("/reassignments")
def reassignments_page():
    """Page listing all reassignment requests; approve/reject before changes are applied."""
    return render_template("reassignments.html")


@app.route("/api/reassignments", methods=["GET"])
def api_reassignments_list():
    return jsonify(reassignments_get_all())


@app.route("/api/reassignments", methods=["POST"])
def api_reassignments_submit():
    """Submit one or more reassignments for approval; sends email to noel.hoxie@databricks.com."""
    data = request.get_json(silent=True) or {}
    if isinstance(data, list):
        items = data
    else:
        items = [data]
    created = []
    for item in items:
        if not item.get("order_id") or not item.get("reroute_site_id"):
            continue
        entry = reassignment_add(
            order_id=item.get("order_id", ""),
            customer_name=item.get("customer_name", ""),
            origin_site_id=item.get("origin_site_id", ""),
            origin_name=item.get("origin_name", ""),
            reroute_site_id=item.get("reroute_site_id", ""),
            reroute_site_name=item.get("reroute_site_name", ""),
            delivery_city=item.get("delivery_city", ""),
            delivery_state=item.get("delivery_state", ""),
            delivery_due_date=item.get("delivery_due_date", ""),
            reroute_plant_new_load=item.get("reroute_plant_new_load"),
            reroute_plant_capacity=item.get("reroute_plant_capacity"),
            reroute_plant_utilization_pct=item.get("reroute_plant_utilization_pct"),
        )
        created.append(entry)
    email_sent = False
    if created:
        base_url = request.host_url
        email_sent = send_approval_email(created, base_url)
        if email_sent:
            mark_email_sent([e["id"] for e in created])
    return jsonify({"created": len(created), "items": created, "email_sent": email_sent})


@app.route("/api/reassignments/<id>/approve", methods=["POST"])
def api_reassignments_approve(id):
    updated = reassignment_set_status(id, "approved")
    if updated is None:
        return jsonify({"error": "Not found or already decided"}), 404
    return jsonify(updated)


@app.route("/api/reassignments/<id>/reject", methods=["POST"])
def api_reassignments_reject(id):
    updated = reassignment_set_status(id, "rejected")
    if updated is None:
        return jsonify({"error": "Not found or already decided"}), 404
    return jsonify(updated)


@app.route("/api/orders")
def api_orders():
    return jsonify({
        "kpis": get_orders_kpis(),
        **get_orders_charts(),
    })


# In-memory edits for sales orders (keyed by order_id) so edits persist in session
_sales_order_edits: dict = {}


@app.route("/api/sales-orders")
def api_sales_orders():
    """List of sales orders (customer orders) for the Sales orders tab. Merges any session edits."""
    orders = get_orders_with_weather()
    for o in orders:
        oid = o.get("order_id")
        if oid and oid in _sales_order_edits:
            o.update({k: v for k, v in _sales_order_edits[oid].items() if v is not None})
    return jsonify({"orders": orders})


@app.route("/api/procurement")
def api_procurement():
    return jsonify({
        "kpis": get_procurement_kpis(),
        **get_procurement_charts(),
    })


@app.route("/api/supplier-scorecard")
def api_supplier_scorecard():
    """List of suppliers with scorecard summary (score, tier, on-time %, quality %, lead time, spend)."""
    return jsonify({"suppliers": get_supplier_scorecard()})


@app.route("/api/supplier-scorecard/<path:vendor_id>")
def api_supplier_scorecard_detail(vendor_id):
    """Full scorecard detail for one supplier (for detail view and PDF export)."""
    detail = get_supplier_scorecard_detail(vendor_id)
    if detail is None:
        return jsonify({"error": "Supplier not found"}), 404
    return jsonify(detail)


@app.route("/api/purchase-orders", methods=["GET"])
def api_purchase_orders_list():
    """List of all outstanding purchase orders."""
    return jsonify({"purchase_orders": get_outstanding_pos()})


@app.route("/api/purchase-orders/<path:po_number>", methods=["PATCH"])
def api_purchase_orders_update(po_number):
    """Update a purchase order. Body: vendor?, value?, order_date?, delivery_date?, status?."""
    data = request.get_json() or {}
    updated = update_purchase_order(
        po_number,
        vendor=data.get("vendor"),
        value=float(data["value"]) if data.get("value") is not None else None,
        order_date=data.get("order_date"),
        delivery_date=data.get("delivery_date"),
        status=data.get("status"),
    )
    if updated is None:
        return jsonify({"error": "Purchase order not found"}), 404
    return jsonify(updated)


@app.route("/api/purchase-orders", methods=["POST"])
def api_purchase_orders_create():
    """Create a new purchase order. Body: vendor, order_date, delivery_date (optional), line_items [{ description, quantity, unit_price }], notes (optional)."""
    data = request.get_json() or {}
    vendor = (data.get("vendor") or "").strip()
    order_date = (data.get("order_date") or "").strip()
    delivery_date = (data.get("delivery_date") or "").strip() or None
    line_items = data.get("line_items") or []
    notes = (data.get("notes") or "").strip() or None

    if not vendor:
        return jsonify({"error": "Vendor is required"}), 400
    if not order_date:
        return jsonify({"error": "Order date is required"}), 400
    if not line_items or not isinstance(line_items, list):
        return jsonify({"error": "At least one line item is required"}), 400

    total = 0
    validated_lines = []
    for i, line in enumerate(line_items):
        if not isinstance(line, dict):
            continue
        qty = float(line.get("quantity") or 0)
        price = float(line.get("unit_price") or 0)
        desc = (line.get("description") or "").strip()
        if qty <= 0 or price < 0:
            return jsonify({"error": f"Line {i + 1}: quantity must be positive and unit price non-negative"}), 400
        total += qty * price
        validated_lines.append({"description": desc or None, "quantity": qty, "unit_price": price})

    if not validated_lines:
        return jsonify({"error": "At least one line item with quantity and unit price is required"}), 400

    try:
        po = add_purchase_order(
            vendor=vendor,
            order_date=order_date,
            value=total,
            delivery_date=delivery_date,
            line_items=validated_lines,
            notes=notes,
        )
    except Exception as e:
        log.exception("Create PO failed: %s", e)
        return jsonify({"error": "Failed to save purchase order"}), 500
    return jsonify(po), 201


@app.route("/api/purchase-orders/upload", methods=["POST"])
def api_purchase_orders_upload():
    """Upload purchase orders from a CSV file. CSV must have header row with: vendor, order_date, quantity, unit_price; optional: delivery_date, description, notes."""
    import csv
    import io

    if "file" not in request.files:
        return jsonify({"error": "No file provided", "created": 0, "errors": []}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "No file selected", "created": 0, "errors": []}), 400
    if not f.filename.lower().endswith(".csv"):
        return jsonify({"error": "File must be a CSV", "created": 0, "errors": []}), 400

    try:
        content = f.read().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError:
        return jsonify({"error": "File must be UTF-8 encoded", "created": 0, "errors": []}), 400

    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return jsonify({"error": "CSV has no header row", "created": 0, "errors": []}), 400

    # Normalize column names (strip, lower)
    fieldnames = [str(h).strip().lower().replace(" ", "_") for h in reader.fieldnames]
    required = {"vendor", "order_date", "quantity", "unit_price"}
    if not required.issubset(set(fieldnames)):
        return jsonify({
            "error": "CSV must include columns: vendor, order_date, quantity, unit_price",
            "created": 0,
            "errors": [],
        }), 400

    created = 0
    errors = []
    for i, row in enumerate(reader):
        row_num = i + 2  # 1-based, +1 for header
        # Map row by normalized keys
        r = {k: (row.get(h) or "").strip() for h, k in zip(reader.fieldnames, fieldnames)}
        vendor = (r.get("vendor") or "").strip()
        order_date = (r.get("order_date") or "").strip()
        delivery_date = (r.get("delivery_date") or "").strip() or None
        description = (r.get("description") or "").strip() or None
        notes = (r.get("notes") or "").strip() or None
        try:
            qty = float(r.get("quantity") or "0")
            price = float(r.get("unit_price") or "0")
        except (TypeError, ValueError):
            errors.append({"row": row_num, "message": "Invalid quantity or unit_price"})
            continue
        if not vendor:
            errors.append({"row": row_num, "message": "Vendor is required"})
            continue
        if not order_date:
            errors.append({"row": row_num, "message": "Order date is required"})
            continue
        if qty <= 0 or price < 0:
            errors.append({"row": row_num, "message": "Quantity must be positive and unit_price non-negative"})
            continue
        try:
            add_purchase_order(
                vendor=vendor,
                order_date=order_date,
                value=qty * price,
                delivery_date=delivery_date,
                line_items=[{"description": description, "quantity": qty, "unit_price": price}],
                notes=notes,
            )
            created += 1
        except Exception as e:
            log.warning("Upload PO row %s failed: %s", row_num, e)
            errors.append({"row": row_num, "message": str(e)})

    return jsonify({"created": created, "errors": errors})

@app.route("/api/inventory-optimization")
def api_inventory_optimization():
    return jsonify({
        "kpis": get_inventory_optimization_kpis(),
        **get_inventory_optimization_charts(),
    })


@app.route("/api/production")
def api_production():
    return jsonify({
        "kpis": get_production_kpis(),
        **get_production_charts(),
        "oee_forecast_7d": get_production_oee_forecast_7d(),
    })


@app.route("/api/production-orders")
def api_production_orders():
    """Production orders list for the Production orders tab (table with filters)."""
    return jsonify({"production_orders": get_production_orders()})


@app.route("/api/production-orders/<path:order_id>", methods=["PATCH"])
def api_production_orders_update(order_id):
    """Update a production order. Body: material?, plant?, quantity?, status?, start_date?, end_date?."""
    data = request.get_json() or {}
    q = data.get("quantity")
    updated = update_production_order(
        order_id,
        material=data.get("material"),
        plant=data.get("plant"),
        quantity=int(q) if q is not None else None,
        status=data.get("status"),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
    )
    if updated is None:
        return jsonify({"error": "Production order not found"}), 404
    return jsonify(updated)


@app.route("/api/sales-orders/<path:order_id>", methods=["PATCH"])
def api_sales_orders_update(order_id):
    """Update a sales order (session-only). Body: status?, customer_name?, delivery_city?, delivery_state?, order_date?, delivery_due_date?, total_usd?, item_count?."""
    data = request.get_json() or {}
    if order_id not in _sales_order_edits:
        _sales_order_edits[order_id] = {}
    allowed = ("status", "customer_name", "delivery_city", "delivery_state", "order_date", "delivery_due_date", "total_usd", "item_count")
    for k in allowed:
        if k in data:
            _sales_order_edits[order_id][k] = data[k]
    return jsonify({"order_id": order_id, "updated": _sales_order_edits[order_id]})


@app.route("/api/tariffs")
def api_tariffs():
    """US tariff rates from Data.gov catalog and USITC HTS CSV sample."""
    return jsonify(get_tariffs())


@app.route("/api/fred/search")
def api_fred_search():
    """Search FRED for economic data series. Query param: q (search text). Requires FRED_API_KEY."""
    if not FRED_API_KEY:
        return jsonify({"error": "FRED API key not configured. Set FRED_API_KEY in environment."}), 503
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"seriess": [], "error": "Missing query parameter q"})
    try:
        from fred_client import search_series
        seriess = search_series(q, limit=80)
        return jsonify({"seriess": seriess})
    except Exception as e:
        log.exception("FRED search failed")
        return jsonify({"error": str(e), "seriess": []}), 500


@app.route("/api/fred/observations")
def api_fred_observations():
    """Get observations for a FRED series. Query params: series_id, start (optional), end (optional)."""
    if not FRED_API_KEY:
        return jsonify({"error": "FRED API key not configured. Set FRED_API_KEY in environment."}), 503
    series_id = request.args.get("series_id", "").strip()
    if not series_id:
        return jsonify({"error": "Missing series_id", "observations": []}), 400
    start = request.args.get("start", "").strip() or None
    end = request.args.get("end", "").strip() or None
    try:
        from fred_client import get_observations
        obs = get_observations(series_id, observation_start=start, observation_end=end)
        return jsonify({"series_id": series_id, "observations": obs})
    except Exception as e:
        log.exception("FRED observations failed")
        return jsonify({"error": str(e), "observations": []}), 500


@app.route("/api/forecast", methods=["POST"])
def api_forecast():
    """
    Build a forecast from one or more FRED series.
    Body: { "series_ids": ["GDP", "UNRATE"], "observation_start": "2020-01-01", "observation_end": "2024-12-31", "method": "linear", "forecast_periods": 12 }.
    Returns for each series: historical dates/values and forecast dates/values.
    """
    if not FRED_API_KEY:
        return jsonify({"error": "FRED API key not configured. Set FRED_API_KEY in environment."}), 503
    data = request.get_json(silent=True) or {}
    series_ids = data.get("series_ids") or []
    if not series_ids:
        return jsonify({"error": "series_ids required", "series": {}}), 400
    if isinstance(series_ids, str):
        series_ids = [s.strip() for s in series_ids.split(",") if s.strip()]
    observation_start = data.get("observation_start", "").strip() or None
    observation_end = data.get("observation_end", "").strip() or None
    method = (data.get("method") or "linear").strip().lower()
    if method not in ("linear", "last", "exponential_smoothing", "arima"):
        method = "linear"
    forecast_periods = max(1, min(60, int(data.get("forecast_periods") or 12)))
    try:
        from fred_client import get_observations
        import numpy as np
        from datetime import datetime, timedelta
    except ImportError as e:
        return jsonify({"error": "numpy required for forecasting: " + str(e), "series": {}}), 500
    if method in ("exponential_smoothing", "arima"):
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
            from statsmodels.tsa.arima.model import ARIMA
        except ImportError:
            return jsonify({"error": "statsmodels required for exponential smoothing and ARIMA. Install with: pip install statsmodels", "series": {}}), 500

    def _next_month(y, m):
        m += 1
        if m > 12:
            m, y = 1, y + 1
        return y, m

    def _forecast_values(values, method, forecast_periods):
        """Return list of forecast values; uses last value on failure."""
        n = len(values)
        if n < 3:
            return [values[-1]] * forecast_periods if values else [0.0] * forecast_periods
        arr = np.asarray(values, dtype=float)
        if method == "exponential_smoothing":
            try:
                model = ExponentialSmoothing(arr, trend="add", seasonal=None)
                fit = model.fit(optimized=True)
                return fit.forecast(steps=forecast_periods).tolist()
            except Exception:
                return [float(arr[-1])] * forecast_periods
        if method == "arima":
            try:
                model = ARIMA(arr, order=(1, 1, 1))
                fit = model.fit()
                return fit.forecast(steps=forecast_periods).tolist()
            except Exception:
                return [float(arr[-1])] * forecast_periods
        return None

    result = {}
    for sid in series_ids[:10]:  # cap at 10 series
        try:
            obs = get_observations(sid, observation_start=observation_start, observation_end=observation_end, limit=2000)
        except Exception as e:
            result[sid] = {"error": str(e), "historical": [], "forecast": []}
            continue
        valid = [(o["date"], float(o["value"])) for o in obs if o.get("value") and str(o["value"]).strip() and str(o["value"]) != "."]
        if not valid:
            result[sid] = {"error": "No valid observations", "historical": [], "forecast": []}
            continue
        dates, values = zip(*valid)
        dates = list(dates)
        values = list(values)
        x = np.arange(len(values))
        if method == "linear":
            coeffs = np.polyfit(x, values, 1)
            extend_x = np.arange(len(values), len(values) + forecast_periods)
            forecast_values = np.polyval(coeffs, extend_x).tolist()
        elif method in ("exponential_smoothing", "arima"):
            forecast_values = _forecast_values(values, method, forecast_periods)
        else:
            last_val = values[-1]
            forecast_values = [last_val] * forecast_periods
        last_date = dates[-1]
        try:
            if len(last_date) >= 7 and last_date[4] == "-":  # YYYY-MM or YYYY-MM-DD
                y, m = int(last_date[:4]), int(last_date[5:7])
                forecast_dates = []
                for _ in range(forecast_periods):
                    y, m = _next_month(y, m)
                    forecast_dates.append(f"{y}-{m:02d}-01")
            else:
                dt = datetime.strptime(last_date[:10], "%Y-%m-%d")
                forecast_dates = [(dt + timedelta(days=30 * (i + 1))).strftime("%Y-%m-%d") for i in range(forecast_periods)]
        except Exception:
            dt = datetime.strptime(last_date[:10], "%Y-%m-%d")
            forecast_dates = [(dt + timedelta(days=30 * (i + 1))).strftime("%Y-%m-%d") for i in range(forecast_periods)]
        result[sid] = {
            "historical": [{"date": d, "value": v} for d, v in zip(dates, values)],
            "forecast": [{"date": d, "value": round(v, 4)} for d, v in zip(forecast_dates, forecast_values)],
        }
    return jsonify({"method": method, "series": result})


@app.route("/api/comments", methods=["GET"])
def api_comments_list():
    tab = request.args.get("tab")
    return jsonify(get_comments(tab=tab))


@app.route("/api/comments", methods=["POST"])
def api_comments_post():
    data = request.get_json() or {}
    tab = data.get("tab", "").strip()
    content = data.get("content", "").strip()
    name = (data.get("name") or "").strip() or None
    if not tab or not content:
        return jsonify({"error": "tab and content required"}), 400
    comment = add_comment(tab=tab, content=content, author_name=name)
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


@app.route("/api/executive-summary")
def api_executive_summary():
    """Combined supply chain data for the executive summary report (one request)."""
    payload = {
        "procurement": {
            "kpis": get_procurement_kpis(),
            **get_procurement_charts(),
        },
        "production": {
            "kpis": get_production_kpis(),
            **get_production_charts(),
        },
    }
    try:
        alerts = get_orders_weather_alerts_with_reroute()
        payload["weather_alerts_count"] = len(alerts) if isinstance(alerts, list) else 0
    except Exception:
        payload["weather_alerts_count"] = 0
    return jsonify(payload)


def _baseline_payload():
    """Build combined payload in the shape expected by the simulator and front-end."""
    return {
        "orders": {
            "kpis": get_orders_kpis(),
            **get_orders_charts(),
        },
        "procurement": {
            "kpis": get_procurement_kpis(),
            **get_procurement_charts(),
        },
        "production": {
            "kpis": get_production_kpis(),
            **get_production_charts(),
            "oee_forecast_7d": get_production_oee_forecast_7d(),
        },
    }


@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    """
    Run disruption simulation on dashboard KPIs and chart data.
    Body: { "disruptions": [ { "type", "severity", "scope" } ] }.
    Returns combined payload: { orders, procurement, production }.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        disruptions = data.get("disruptions") or []
        baseline = _baseline_payload()
        result = run_dashboard_simulation(baseline, disruptions)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(__import__("os").environ.get("PORT", 5000)), debug=False)
