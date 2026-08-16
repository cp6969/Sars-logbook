"""Plain psycopg connection helpers -- no ORM, mirrors the sibling PO Bridge
app's own database.py convention (fetchone/fetchall/execute over a raw
connection, with a connect timeout + a few silent retries for a transient
network blip)."""
import time

import psycopg
from psycopg.rows import dict_row

from app.config import settings

_CONNECT_RETRIES = 3
_CONNECT_TIMEOUT = 10


def get_conn():
    last_exc = None
    for _ in range(_CONNECT_RETRIES):
        try:
            return psycopg.connect(
                settings.database_url,
                connect_timeout=_CONNECT_TIMEOUT,
                row_factory=dict_row,
                options="-c statement_timeout=30000",
            )
        except psycopg.OperationalError as exc:
            last_exc = exc
            time.sleep(1)
    raise last_exc


def fetchone(query, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.fetchone()


def fetchall(query, params=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.fetchall()


def execute(query, params=None):
    """Runs a write query. If the query has a RETURNING clause (or is
    otherwise a query with a result set), returns the fetched rows;
    otherwise returns None."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            conn.commit()
            if cur.description:
                return cur.fetchall()
            return None
