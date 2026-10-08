"""Database connection and demo database bootstrap."""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine

from opspulse import config
from opspulse.data import synthetic

SCHEMA_SQLITE = Path(__file__).with_name("schema_sqlite.sql")


def make_engine(url: str | None = None) -> Engine:
    url = url or config.database_url()
    if url.startswith("sqlite"):
        Path(url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
        eng = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(eng, "connect")
        def _fk_on(dbapi_conn, _):          # SQLite enforces foreign keys only when asked
            dbapi_conn.execute("PRAGMA foreign_keys = ON")
        return eng
    # PostgreSQL / Supabase.  pool_pre_ping survives idle connections being closed.
    return create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2)


def load_frames(engine: Engine, frames: dict[str, pd.DataFrame], chunk: int = 2000) -> None:
    """Insert generated frames in foreign-key order (works on SQLite and PostgreSQL)."""
    with engine.begin() as conn:
        for table in synthetic.TABLE_ORDER:
            df = frames[table]
            if df.empty:
                continue
            cols = list(df.columns)
            placeholders = ", ".join(f":{c}" for c in cols)
            sql = text(f"insert into {table} ({', '.join(cols)}) values ({placeholders})")
            records = df.astype(object).where(df.notna(), None).to_dict("records")
            if engine.dialect.name == "postgresql":
                for r in records:     # postgres booleans
                    for b in ("is_demo", "is_active"):
                        if b in r and r[b] is not None:
                            r[b] = bool(r[b])
            for i in range(0, len(records), chunk):
                conn.execute(sql, records[i:i + chunk])


def ensure_demo_database(engine: Engine) -> bool:
    """Create and fill the local SQLite demo database on first run.

    Returns True when the demo data was (re)built.  Only ever touches SQLite."""
    if engine.dialect.name != "sqlite":
        return False
    with engine.connect() as conn:
        has_tables = inspect(conn).has_table("kpi_observations")
        if has_tables:
            n = conn.execute(text("select count(*) from kpi_observations")).scalar()
            if n:
                return False
    # Build into a temporary file, then swap it in, so two visitors arriving at the
    # same moment can never see (or create) a half-built database.
    final = Path(engine.url.database)
    tmp = final.with_suffix(f".building-{os.getpid()}-{threading.get_ident()}")
    tmp.unlink(missing_ok=True)
    with sqlite3.connect(tmp) as raw:
        raw.executescript(SCHEMA_SQLITE.read_text())
    tmp_engine = make_engine(f"sqlite:///{tmp}")
    load_frames(tmp_engine, synthetic.generate())
    tmp_engine.dispose()
    engine.dispose()
    os.replace(tmp, final)
    return True
