"""PostgreSQL connection pool — works with Supabase, Neon, RDS, or any standard PostgreSQL."""
import psycopg2
import psycopg2.pool
import psycopg2.extras
import config

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        if not config.DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is not set. "
                "Add your Supabase connection string as the DATABASE_URL environment variable."
            )
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=8, dsn=config.DATABASE_URL
        )
    return _pool


def run_query(sql: str, params=None) -> tuple[bool, list[dict]]:
    try:
        pool = _get_pool()
    except Exception as e:
        return False, [{"error": f"DB pool error: {e}"}]
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
        return True, rows
    except Exception as e:
        conn.rollback()
        return False, [{"error": str(e)}]
    finally:
        pool.putconn(conn)


def run_write(sql: str, params=None, returning: bool = True) -> tuple[bool, dict | int]:
    try:
        pool = _get_pool()
    except Exception as e:
        return False, {"error": f"DB pool error: {e}"}
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if returning and cur.description:
                result = dict(cur.fetchone())
            else:
                result = cur.rowcount
        conn.commit()
        return True, result
    except Exception as e:
        conn.rollback()
        return False, {"error": str(e)}
    finally:
        pool.putconn(conn)
