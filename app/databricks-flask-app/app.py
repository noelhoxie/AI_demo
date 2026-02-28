import os
import logging
from flask import Flask, render_template, request, jsonify
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState
from dotenv import load_dotenv

# load_dotenv is a no-op when env vars are already set (inside Databricks Apps)
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
DEFAULT_CATALOG = os.environ.get("DEFAULT_CATALOG", "main")
DEFAULT_SCHEMA = os.environ.get("DEFAULT_SCHEMA", "default")
QUERY_ROW_LIMIT = int(os.environ.get("QUERY_ROW_LIMIT", "500"))

if not WAREHOUSE_ID:
    log.warning(
        "DATABRICKS_WAREHOUSE_ID is not set — SQL execution endpoints will return errors."
    )

# ── SDK Client ────────────────────────────────────────────────────────────────
# WorkspaceClient() uses Databricks unified auth:
#   Inside Databricks Apps → reads DATABRICKS_HOST + injected service-principal creds
#   Locally              → reads DATABRICKS_HOST + DATABRICKS_TOKEN from .env
_ws_client: WorkspaceClient | None = None


def get_client() -> WorkspaceClient:
    """Return a lazily-initialised, module-level WorkspaceClient."""
    global _ws_client
    if _ws_client is None:
        _ws_client = WorkspaceClient()
    return _ws_client


# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(
        "index.html",
        default_catalog=DEFAULT_CATALOG,
        default_schema=DEFAULT_SCHEMA,
    )


# ── API routes ────────────────────────────────────────────────────────────────

@app.route("/api/schemas")
def list_schemas():
    """GET /api/schemas?catalog=<name> — list schemas in a Unity Catalog catalog."""
    catalog_name = request.args.get("catalog", DEFAULT_CATALOG)
    try:
        w = get_client()
        schemas = [
            s.name
            for s in w.schemas.list(catalog_name=catalog_name)
            if s.name
        ]
        return jsonify({"catalog": catalog_name, "schemas": schemas})
    except Exception as exc:
        log.exception("Failed to list schemas in catalog %s", catalog_name)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/tables")
def list_tables():
    """GET /api/tables?catalog=<cat>&schema=<schema> — list tables in a schema."""
    catalog_name = request.args.get("catalog", DEFAULT_CATALOG)
    schema_name = request.args.get("schema", DEFAULT_SCHEMA)
    try:
        w = get_client()
        tables = [
            {
                "name": t.name,
                "full_name": t.full_name,
                "table_type": t.table_type.value if t.table_type else "UNKNOWN",
            }
            for t in w.tables.list(
                catalog_name=catalog_name,
                schema_name=schema_name,
            )
            if t.name
        ]
        return jsonify({
            "catalog": catalog_name,
            "schema": schema_name,
            "tables": tables,
        })
    except Exception as exc:
        log.exception("Failed to list tables in %s.%s", catalog_name, schema_name)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/query", methods=["POST"])
def run_query():
    """
    POST /api/query
    Body: {"sql": "SELECT ...", "catalog": "...", "schema": "..."}
    Executes SQL on the configured warehouse and returns
    {"columns": [...], "rows": [[...], ...], "row_count": N, "truncated": bool}
    """
    if not WAREHOUSE_ID:
        return jsonify({"error": "DATABRICKS_WAREHOUSE_ID is not configured"}), 500

    body = request.get_json(silent=True) or {}
    sql = (body.get("sql") or "").strip()
    catalog = body.get("catalog", DEFAULT_CATALOG)
    schema = body.get("schema", DEFAULT_SCHEMA)

    if not sql:
        return jsonify({"error": "No SQL statement provided"}), 400

    try:
        w = get_client()
        response = w.statement_execution.execute_statement(
            statement=sql,
            warehouse_id=WAREHOUSE_ID,
            catalog=catalog,
            schema=schema,
            wait_timeout="50s",
            row_limit=QUERY_ROW_LIMIT,
        )

        state = response.status.state
        if state != StatementState.SUCCEEDED:
            error_msg = (
                response.status.error.message
                if response.status.error
                else f"Statement ended in state: {state}"
            )
            return jsonify({"error": error_msg}), 400

        manifest = response.result.manifest
        columns = [col.name for col in manifest.schema.columns]
        chunk = response.result.data_array or []
        rows = [list(row) for row in chunk]

        return jsonify({
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": len(rows) == QUERY_ROW_LIMIT,
        })

    except Exception as exc:
        log.exception("Query execution failed: %s", sql[:200])
        return jsonify({"error": str(exc)}), 500


# ── Local dev entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("DATABRICKS_APP_PORT", 8000))
    # Use debug mode only locally (Databricks Apps injects DATABRICKS_CLIENT_ID)
    debug = os.environ.get("DATABRICKS_CLIENT_ID") is None
    log.info("Starting Flask dev server on port %d (debug=%s)", port, debug)
    app.run(host="0.0.0.0", port=port, debug=debug)
