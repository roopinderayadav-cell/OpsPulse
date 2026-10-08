"""Central settings.  Secrets are read from Streamlit Secrets or environment
variables - never from code.  Nothing in this file is a password or key."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "OpsPulse AI"
TAGLINE = "From Data to Decisions"
VERSION = "0.1.0 (Phase 1 - Module 1)"

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DEMO_DB_PATH = DATA_DIR / "opspulse_demo.db"

# Default AI models (can be overridden with GEMINI_MODEL in Secrets)
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"

# Default health-score rules.  Each organisation can override these in
# organizations.settings -> "health".  Kept here so the rule is visible in one place.
DEFAULT_HEALTH_RULES = {
    "points": {"green": 100, "amber": 60, "red": 20},   # points a KPI earns for its RAG status
    "bands": {"green": 90, "amber": 75},                 # score >= 90 Green, >= 75 Amber, else Red
    "min_coverage": 0.60,                                # below this share of expected data -> "Insufficient data"
}


def secret(name: str, default: str | None = None) -> str | None:
    """Read a setting from the environment first, then Streamlit Secrets."""
    val = os.environ.get(name)
    if val:
        return val
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:          # no secrets file at all is normal in local demo mode
        pass
    return default


def database_url() -> str:
    """PostgreSQL/Supabase if DATABASE_URL is set, otherwise the local demo SQLite file."""
    url = secret("DATABASE_URL")
    if url:
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url
    return f"sqlite:///{DEMO_DB_PATH}"


def is_demo_database() -> bool:
    return database_url().startswith("sqlite")
