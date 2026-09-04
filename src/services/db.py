"""Optional database-backed store (Postgres/SQLite via SQLAlchemy).

When DATABASE_URL is set, portal state (scores, alerts, features snapshot,
intervention log, alert actions) lives in the database instead of CSV files:
tables are created and seeded idempotently from the bundled batch artifacts on
first use, and subsequent reads/writes go to the DB. Without DATABASE_URL the
existing file-backed path (store.py) is used unchanged.

Set DATABASE_URL like:
  postgresql+psycopg2://user:pass@host:5432/dbname      (Render Postgres internal URL)
  sqlite:///data/dev.sqlite3                            (local smoke tests)
"""
import os

import pandas as pd
from sqlalchemy import create_engine, text

# kind -> (table name, primary key)
TABLES = {
    "scores": ("risk_scores", "customer_id"),
    "alerts": ("alerts", "customer_id"),
    "features": ("features", "customer_id"),
    "interventions": ("intervention_log", "id"),
    "alert_actions": ("alert_actions", "id"),
}

# kinds keyed by scoring_date (seeded per cycle); others are append-only logs
_CYCLE_TYPES = {"scores", "alerts", "features"}

_engine = None


def enabled() -> bool:
    return bool(os.environ.get("DATABASE_URL", "").strip())


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    return _engine


def _table(kind):
    name, _pk = TABLES[kind]
    return name


def _table_exists(kind) -> bool:
    from sqlalchemy import inspect
    return _table(kind) in inspect(get_engine()).get_table_names()


def _has_rows(kind, scoring_date=None) -> bool:
    if not _table_exists(kind):
        return False
    sql = f'SELECT 1 FROM "{_table(kind)}"'
    params = {}
    if scoring_date is not None:
        sql += " WHERE scoring_date = :sd"
        params["sd"] = str(scoring_date)
    sql += " LIMIT 1"
    with get_engine().connect() as conn:
        return conn.execute(text(sql), params).first() is not None


def seed(kind, df: pd.DataFrame, scoring_date=None):
    """Create the table if needed and insert rows when empty for this cycle."""
    if df is None or len(df) == 0:
        return
    # stamp the cycle so per-date reads work for kinds whose bundle lacks it
    if scoring_date is not None and "scoring_date" not in df.columns:
        df = df.copy()
        df["scoring_date"] = str(scoring_date)
    if not _table_exists(kind):
        with get_engine().begin() as conn:
            df.to_sql(_table(kind), conn, if_exists="append", index=False)
        return
    if _has_rows(kind, scoring_date):
        return
    with get_engine().begin() as conn:
        df.to_sql(_table(kind), conn, if_exists="append", index=False)


def read(kind, scoring_date=None):
    """Read a full-frame for the kind, seeding from bundled files when needed.

    Callers must pass the same dataframe used for seeding; returns an empty
    frame when nothing is available yet.
    """
    sql = f'SELECT * FROM "{_table(kind)}"'
    params = {}
    if scoring_date is not None:
        sql += " WHERE scoring_date = :sd"
        params["sd"] = str(scoring_date)
    try:
        return pd.read_sql_query(sql, get_engine(), params=params)
    except Exception:
        return pd.DataFrame()


def append(kind, row: dict):
    """Append one row (intervention / alert action audit record); creates the
    table on first write if needed."""
    df = pd.DataFrame([row])
    with get_engine().begin() as conn:
        df.to_sql(_table(kind), conn, if_exists="append", index=False)
    return row
