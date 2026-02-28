"""
PostgreSQL connection utilities for Databricks / OAuth and env-based config.
Extracted for reuse by Dash, API, or notebook apps.

Uses:
  - PGDATABASE, PGUSER, PGHOST, PGPORT, PGSSLMODE, PGAPPNAME from environment
  - OAuth token from Databricks WorkspaceClient as password (when available)
  - Connection pool (psycopg_pool) for server apps

Usage:
  from db_connection import get_connection, get_schema_name, get_connection_string

  with get_connection() as conn:
      with conn.cursor() as cur:
          cur.execute("SELECT 1")
  schema = get_schema_name()
"""

import os
import time
from typing import Optional

# Optional: only used when Databricks SDK and pool are available
workspace_client = None
postgres_password: Optional[str] = None
last_password_refresh: float = 0
connection_pool = None

try:
    from databricks import sdk
    workspace_client = sdk.WorkspaceClient()
except Exception:
    pass

try:
    from psycopg_pool import ConnectionPool
except ImportError:
    ConnectionPool = None


def refresh_oauth_token() -> bool:
    """Refresh OAuth token if expired (Databricks)."""
    global postgres_password, last_password_refresh
    if workspace_client is None:
        return False
    if postgres_password is None or time.time() - last_password_refresh > 900:
        print("Refreshing PostgreSQL OAuth token")
        try:
            postgres_password = workspace_client.config.oauth_token().access_token
            last_password_refresh = time.time()
        except Exception as e:
            print(f"❌ Failed to refresh OAuth token: {str(e)}")
            return False
    return True


def get_connection_string(use_oauth: bool = True) -> str:
    """
    Build PostgreSQL connection string from environment and optional OAuth.

    Env: PGDATABASE, PGUSER, PGHOST, PGPORT, PGSSLMODE (default require), PGAPPNAME.
    If use_oauth and Databricks is available, password is the OAuth token (call refresh_oauth_token first).
    Otherwise password comes from PGPASSWORD.
    """
    password = os.getenv("PGPASSWORD", "")
    if use_oauth and workspace_client is not None:
        refresh_oauth_token()
        if postgres_password is not None:
            password = postgres_password
    return (
        f"dbname={os.getenv('PGDATABASE', '')} "
        f"user={os.getenv('PGUSER', '')} "
        f"password={password} "
        f"host={os.getenv('PGHOST', '')} "
        f"port={os.getenv('PGPORT', '5432')} "
        f"sslmode={os.getenv('PGSSLMODE', 'require')} "
        f"application_name={os.getenv('PGAPPNAME', 'app')}"
    )


def get_connection_pool(min_size: int = 2, max_size: int = 10):
    """Get or create the connection pool. Uses get_connection_string(use_oauth=True)."""
    global connection_pool
    if ConnectionPool is None:
        raise RuntimeError("psycopg_pool not installed")
    if connection_pool is None:
        refresh_oauth_token()
        conn_string = get_connection_string(use_oauth=True)
        connection_pool = ConnectionPool(conn_string, min_size=min_size, max_size=max_size)
    return connection_pool


def get_connection(use_pool: bool = True):
    """
    Get a connection. Recreates pool if OAuth token expired.

    If use_pool and psycopg_pool is available, returns a connection from the pool.
    Otherwise opens a new connection using get_connection_string().
    """
    global connection_pool

    if postgres_password is None or time.time() - last_password_refresh > 900:
        if connection_pool is not None:
            try:
                connection_pool.close()
            except Exception:
                pass
            connection_pool = None

    if use_pool and ConnectionPool is not None:
        return get_connection_pool().connection()

    import psycopg
    return psycopg.connect(get_connection_string(use_oauth=True))


def get_schema_name() -> str:
    """Schema name in the format {PGAPPNAME}_schema_{PGUSER} (PGUSER normalized: dashes removed)."""
    pgappname = os.getenv("PGAPPNAME", "my_app")
    pguser = (os.getenv("PGUSER", "") or "").replace("-", "")
    return f"{pgappname}_schema_{pguser}"
