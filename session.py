"""Shared, cached services for every page: database, current user, organisation, analyzer."""
from __future__ import annotations

import hmac
from dataclasses import dataclass

import streamlit as st

from opspulse import config
from opspulse.data import db, repository
from opspulse.engine.analytics import Analyzer

DEMO_USER_EMAIL = "demo.executive@example.com"


@st.cache_resource(show_spinner=False)
def get_engine(url: str):
    eng = db.make_engine(url)
    db.ensure_demo_database(eng)          # only acts on the local SQLite demo database
    return eng


@st.cache_resource(show_spinner=False, max_entries=20)
def get_analyzer(url: str, org_id: str, data_version: int) -> Analyzer:
    """One analyzer per organisation (its internal cache makes reruns fast).
    ``data_version`` changes when data is reloaded, which builds a fresh one."""
    return Analyzer(repository.load_bundle(get_engine(url), org_id))


@dataclass
class Context:
    engine: object
    url: str
    user: dict
    org_id: str
    org_name: str
    role: str
    analyzer: Analyzer


def access_gate() -> bool:
    """Optional shared access code for private demos (APP_ACCESS_CODE in Secrets).
    Real per-user sign-in (Supabase Auth) is planned for Phase 2."""
    code = config.secret("APP_ACCESS_CODE")
    if not code or st.session_state.get("gate_ok"):
        return True
    left, mid, right = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("### OpsPulse AI")
        st.caption("Private demonstration. Enter the access code you were given.")
        with st.form("gate"):
            entered = st.text_input("Access code", type="password")
            if st.form_submit_button("Continue", type="primary", width="stretch"):
                if hmac.compare_digest(entered.encode(), code.encode()):
                    st.session_state.gate_ok = True
                    st.rerun()
                st.error("That code is not correct.")
    return False


def load_context() -> Context:
    url = config.database_url()
    engine = get_engine(url)
    email = config.secret("DEMO_USER_EMAIL", DEMO_USER_EMAIL)
    user = repository.user_by_email(engine, email)
    if not user:
        raise LookupError(f"No user with e-mail {email} exists in the database.")
    user["id"] = str(user["id"])
    orgs = repository.organizations_for_user(engine, user["id"])
    if orgs.empty:
        raise LookupError("This user is not an active member of any organisation.")
    orgs["id"] = orgs["id"].astype(str)
    ids = list(orgs["id"])
    if st.session_state.get("org_id") not in ids:
        st.session_state.org_id = ids[0]
    if len(ids) > 1:
        names = dict(zip(orgs["id"], orgs["name"]))
        st.sidebar.selectbox("Organisation", ids, key="org_id", format_func=names.get)
    row = orgs[orgs["id"] == st.session_state.org_id].iloc[0]
    analyzer = get_analyzer(url, row["id"], st.session_state.get("data_version", 0))
    return Context(engine, url, user, row["id"], row["name"], row["role"], analyzer)
