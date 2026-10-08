"""Load the SYNTHETIC demo organisation into a PostgreSQL / Supabase database.

Usage (run on your own computer, never commit the connection string):
    set DATABASE_URL=postgresql://...        (Windows)   |   export DATABASE_URL=...  (Mac/Linux)
    python load_demo_data.py

The migrations in supabase/migrations must already have been run.
Safe to re-run: it stops if the demo organisation already exists.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text  # noqa: E402

import op_config as config  # noqa: E402
import op_db as db, op_synthetic as synthetic  # noqa: E402


def main(url: str | None = None) -> int:
    url = url or config.database_url()
    if url.startswith("sqlite"):
        print("DATABASE_URL is not set - nothing to do (the local demo database builds itself).")
        return 1
    engine = db.make_engine(url)
    with engine.connect() as conn:
        exists = conn.execute(text("select 1 from organizations where id = :i"), {"i": synthetic.ORG_ID}).first()
    if exists:
        print("The synthetic demo organisation is already loaded - nothing changed.")
        return 0
    frames = synthetic.generate()
    db.load_frames(engine, frames)
    print(f"Loaded synthetic demo data: {len(frames['kpi_observations']):,} KPI observations, "
          f"{len(frames['organizational_units'])} units, {len(frames['kpi_definitions'])} KPIs.")
    print("Note: demo users must also exist in Supabase Auth to sign in once authentication arrives (Phase 2).")
    return 0


if __name__ == "__main__":
    sys.exit(main(os.environ.get("DATABASE_URL") and config.database_url()))
