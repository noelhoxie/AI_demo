"""
Comments stored in Postgres (Databricks Postgres or external).
Uses db_connection when available; falls back to psycopg with env (PGHOST, PGDATABASE, PGUSER, PGPASSWORD).
"""
import logging
import os
from datetime import datetime
from typing import Any, Optional

from config import postgres_configured

log = logging.getLogger(__name__)

# Optional: use shared db_connection from repo root
try:
    import sys
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from db_connection import get_connection, get_schema_name
    _use_db_connection = True
except ImportError:
    _use_db_connection = False


def _get_conn():
    if not postgres_configured():
        return None
    if _use_db_connection:
        try:
            return get_connection(use_pool=True)
        except Exception as e:
            log.warning("db_connection failed: %s", e)
    try:
        import psycopg
        return psycopg.connect(
            host=os.environ.get("PGHOST"),
            dbname=os.environ.get("PGDATABASE"),
            user=os.environ.get("PGUSER"),
            password=os.environ.get("PGPASSWORD", ""),
            port=os.environ.get("PGPORT", "5432"),
            connect_timeout=5,
        )
    except Exception as e:
        log.exception("Postgres connect failed: %s", e)
        return None


def _schema_table():
    if _use_db_connection:
        try:
            schema = get_schema_name()
            return schema, "dashboard_comments"
        except Exception:
            pass
    return "public", "dashboard_comments"


def init_comments_table() -> bool:
    """Create schema (if needed) and dashboard_comments table. Returns True if ready."""
    conn = _get_conn()
    if not conn:
        return False
    schema, table = _schema_table()
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS "{schema}"."{table}" (
                    id SERIAL PRIMARY KEY,
                    tab TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute(f'ALTER TABLE "{schema}"."{table}" ADD COLUMN IF NOT EXISTS author_name TEXT')
        conn.commit()
        return True
    except Exception as e:
        log.exception("Init comments table failed: %s", e)
        conn.rollback()
        return False
    finally:
        conn.close()


def get_comments(tab: Optional[str] = None) -> list[dict[str, Any]]:
    """List comments, optionally filtered by tab."""
    conn = _get_conn()
    if not conn:
        return []
    schema, table = _schema_table()
    try:
        with conn.cursor() as cur:
            if tab:
                cur.execute(
                    f'SELECT id, tab, content, created_at, COALESCE(author_name, \'\') FROM "{schema}"."{table}" WHERE tab = %s ORDER BY created_at DESC',
                    (tab,),
                )
            else:
                cur.execute(f'SELECT id, tab, content, created_at, COALESCE(author_name, \'\') FROM "{schema}"."{table}" ORDER BY created_at DESC')
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "tab": r[1],
                "content": r[2],
                "created_at": r[3].isoformat() if isinstance(r[3], datetime) else str(r[3]),
                "author_name": (r[4] or "").strip() if len(r) > 4 else "",
            }
            for r in rows
        ]
    except Exception as e:
        log.exception("Get comments failed: %s", e)
        return []
    finally:
        conn.close()


def add_comment(tab: str, content: str, author_name: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Insert a comment; return the created row or None. Date is stored as created_at."""
    if not (tab and content and tab.strip() and content.strip()):
        return None
    conn = _get_conn()
    if not conn:
        return None
    schema, table = _schema_table()
    name_val = (author_name or "").strip() or None
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'INSERT INTO "{schema}"."{table}" (tab, content, author_name) VALUES (%s, %s, %s) RETURNING id, tab, content, created_at, author_name',
                (tab.strip(), content.strip(), name_val),
            )
            row = cur.fetchone()
        conn.commit()
        if row:
            return {
                "id": row[0],
                "tab": row[1],
                "content": row[2],
                "created_at": row[3].isoformat() if isinstance(row[3], datetime) else str(row[3]),
                "author_name": (row[4] or "").strip() if len(row) > 4 and row[4] else "",
            }
        return None
    except Exception as e:
        log.exception("Add comment failed: %s", e)
        conn.rollback()
        return None
    finally:
        conn.close()
