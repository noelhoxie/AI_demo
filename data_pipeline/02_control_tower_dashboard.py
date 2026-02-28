# Databricks notebook source
# MAGIC %md
# MAGIC # Supply Chain Control Tower — Databricks
# MAGIC Reads SAP-style data from Delta tables and renders the Control Tower UI with `displayHTML`.
# MAGIC
# MAGIC **Prereqs:** Run `01_setup_sap_delta_tables` once (or have your own Delta tables with the expected columns).

# COMMAND ----------

import json
import os

# COMMAND ----------

# MAGIC %md
# MAGIC ## Config: catalog, schema, and path to HTML
# MAGIC Set via job base_parameters (catalog, schema) or Spark config / widget defaults below.

# COMMAND ----------

dbutils.widgets.text("catalog", spark.conf.get("spark.databricks.sap.catalog", "main"), "Catalog")
dbutils.widgets.text("schema", spark.conf.get("spark.databricks.sap.schema", "sap_control_tower"), "Schema")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

# Path to Control Tower HTML. In Repos use full path, e.g. /Workspace/Repos/<org>/<repo>/supply_chain_control_tower.html
html_path = spark.conf.get("spark.databricks.sap.controlTowerHtml", "supply_chain_control_tower.html")
print(f"Catalog: {catalog}, Schema: {schema}, HTML: {html_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load data from Delta and map to Control Tower JSON
# MAGIC Column names are mapped from SAP-style (Delta) to the keys expected by the front-end.

# COMMAND ----------

def safe_sql(table, default_columns_map):
    """Query Delta table; if missing, return empty list. default_columns_map used when table has different column names."""
    try:
        df = spark.table(f"{catalog}.{schema}.{table}")
        return df.toPandas().to_dict("records")
    except Exception as e:
        print(f"Table {catalog}.{schema}.{table} not found or error: {e}. Using empty data.")
        return []

# COMMAND ----------

# Procurement: ebeln->po, lifnr->vendor, vendor_name->vendorName, matnr->material, menge->qty, netwr->value, status, eindt->delivery
procurement_raw = safe_sql("procurement", {})
procurement = [
    {
        "po": str(r.get("ebeln", r.get("po", ""))),
        "vendor": str(r.get("lifnr", r.get("vendor", ""))),
        "vendorName": str(r.get("vendor_name", r.get("vendorName", r.get("vendor", "")))),
        "material": str(r.get("matnr", r.get("material", ""))),
        "qty": int(r.get("menge", r.get("qty", 0))),
        "value": float(r.get("netwr", r.get("value", 0))),
        "status": str(r.get("status", "Open")),
        "delivery": str(r.get("eindt", r.get("delivery", ""))),
    }
    for r in procurement_raw
]

# Inventory: matnr->material, werks->plant, lgort->storageLoc, unrestricted, blocked, in_transit->inTransit, reorder_point->reorderPoint
inventory_raw = safe_sql("inventory", {})
inventory = [
    {
        "material": str(r.get("matnr", r.get("material", ""))),
        "plant": str(r.get("werks", r.get("plant", ""))),
        "storageLoc": str(r.get("lgort", r.get("storageLoc", ""))),
        "unrestricted": int(r.get("unrestricted", 0)),
        "blocked": int(r.get("blocked", 0)),
        "inTransit": int(r.get("in_transit", r.get("inTransit", 0))),
        "reorderPoint": int(r.get("reorder_point", r.get("reorderPoint", 0))),
    }
    for r in inventory_raw
]

# Manufacturing: aufnr->order, matnr->material, werks->plant, psmng->qty, status, gstrs->start, gltrs->end
manufacturing_raw = safe_sql("manufacturing", {})
manufacturing = [
    {
        "order": str(r.get("aufnr", r.get("order", ""))),
        "material": str(r.get("matnr", r.get("material", ""))),
        "plant": str(r.get("werks", r.get("plant", ""))),
        "qty": int(r.get("psmng", r.get("qty", 0))),
        "status": str(r.get("status", "")),
        "start": str(r.get("gstrs", r.get("start", ""))),
        "end": str(r.get("gltrs", r.get("end", ""))),
    }
    for r in manufacturing_raw
]

# Logistics: vbeln->delivery, kunnr->shipTo, matnr->material, lfimg->qty, status, lfdat->planned, carrier
logistics_raw = safe_sql("logistics", {})
logistics = [
    {
        "delivery": str(r.get("vbeln", r.get("delivery", ""))),
        "shipTo": str(r.get("kunnr", r.get("shipTo", ""))),
        "material": str(r.get("matnr", r.get("material", ""))),
        "qty": int(r.get("lfimg", r.get("qty", 0))),
        "status": str(r.get("status", "")),
        "planned": str(r.get("lfdat", r.get("planned", ""))),
        "carrier": str(r.get("carrier", "")),
    }
    for r in logistics_raw
]

# Demand: vbeln->order, kunnr->customer, matnr->material, kwmeng->qty, edatu->requestDate, status, forecast_qty->forecastQty
demand_raw = safe_sql("demand", {})
demand = [
    {
        "order": str(r.get("vbeln", r.get("order", ""))),
        "customer": str(r.get("kunnr", r.get("customer", ""))),
        "material": str(r.get("matnr", r.get("material", ""))),
        "qty": int(r.get("kwmeng", r.get("qty", 0))),
        "requestDate": str(r.get("edatu", r.get("requestDate", ""))),
        "status": str(r.get("status", "")),
        "forecastQty": int(r.get("forecast_qty", r.get("forecastQty", 0))),
    }
    for r in demand_raw
]

sap_payload = {
    "procurement": procurement,
    "inventory": inventory,
    "manufacturing": manufacturing,
    "logistics": logistics,
    "demand": demand,
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load HTML and inject Delta data
# MAGIC The Control Tower expects `window.loadSAPData(data)` to be called with the payload.

# COMMAND ----------

try:
    with open(html_path, "r") as f:
        html_base = f.read()
except FileNotFoundError:
    # Fallback: embed a minimal message and the data so you can still debug
    html_base = """
    <html><body style="font-family:sans-serif;padding:2rem;">
    <h1>Supply Chain Control Tower</h1>
    <p>HTML file not found at: """ + html_path + """</p>
    <p>Upload <code>supply_chain_control_tower.html</code> to the same repo or set the path in this notebook.</p>
    <pre id="data"></pre>
    <script>
      var data = """ + json.dumps(sap_payload) + """;
      document.getElementById("data").textContent = JSON.stringify(data, null, 2);
    </script>
    </body></html>
    """

# Inject data so the UI runs with Delta-backed SAP data
inject_script = "<script>window.loadSAPData(" + json.dumps(sap_payload) + ");</script>"
if "window.loadSAPData" in html_base and "</body>" in html_base:
    html_base = html_base.replace("</body>", inject_script + "\n</body>")
else:
    html_base += inject_script

# COMMAND ----------

displayHTML(html_base)
