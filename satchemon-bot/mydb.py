"""Postgres connection pool + cursor context manager.

The pool is created lazily on first use (not at import) so this module — and
anything that imports it, like ``sqlhelper`` — can be imported without a live
database or a populated ``config.yml``. That's what lets the DB helpers be unit
tested against an in-memory SQLite by monkeypatching :func:`db_cursor`
(psycopg2/yaml are imported only inside :func:`_get_pool`, so a test env needs
neither). Production behavior is unchanged: same pool sizing, same
commit-on-success / rollback-on-error semantics.
"""

from contextlib import contextmanager

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        import yaml
        import psycopg2.pool

        with open("config.yml", "r") as f:
            cfg = yaml.safe_load(f)["psql"]
        _pool = psycopg2.pool.SimpleConnectionPool(
            16,
            32,
            user=cfg["user"],
            password=cfg["password"],
            host=cfg["ip"],
            port=cfg["port"],
            database=cfg["dbname"],
        )
    return _pool


@contextmanager
def db_cursor():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            yield cur
            conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)
