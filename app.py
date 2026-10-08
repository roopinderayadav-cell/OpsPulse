"""OpsPulse AI - AI-Powered Operations Intelligence Platform.

Start locally:   streamlit run app.py
Streamlit Cloud: main file path = app.py
"""
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:          # make the opspulse/ package importable on every host
    sys.path.insert(0, str(ROOT))
st.set_page_config(page_title="OpsPulse AI", page_icon=str(ROOT / "icon.svg"), layout="wide",
                   initial_sidebar_state="auto")

import op_config as config  # noqa: E402
import op_provider as ai  # noqa: E402
import op_session as session, op_theme as theme  # noqa: E402
import op_command_center as command_center, op_modules as modules  # noqa: E402

theme.apply()
st.logo(str(ROOT / "logo.svg"), icon_image=str(ROOT / "icon.svg"), size="large")

if not session.access_gate():
    st.stop()

try:
    with st.spinner("Loading OpsPulse…"):
        ctx = session.load_context()
except Exception as exc:   # show a friendly message instead of a stack trace
    st.error("OpsPulse could not load its data.", icon=":material/error:")
    st.caption(f"Details: {type(exc).__name__}: {str(exc)[:300]}")
    st.caption("If you connected Supabase, check DATABASE_URL in Streamlit Secrets. Without DATABASE_URL the app "
               "uses its built-in synthetic demo database.")
    st.stop()


def _page(fn, title, icon, url, default=False):
    def run():
        fn(ctx)
    run.__name__ = url.replace("-", "_")
    return st.Page(run, title=title, icon=icon, url_path=url, default=default)


pages = {
    "Overview": [
        _page(command_center.render, "Executive Command Center", ":material/space_dashboard:", "command-center", True),
        st.Page(modules.planned("mobile"), title="Leadership Mobile", icon=":material/smartphone:", url_path="mobile"),
    ],
    "Performance": [
        st.Page(modules.planned("analytics"), title="Process Analytics", icon=":material/monitoring:", url_path="analytics"),
        st.Page(modules.planned("ai"), title="AI Operations Analyst", icon=":material/psychology:", url_path="ai-analyst"),
        st.Page(modules.planned("ppt"), title="PowerPoint Review Studio", icon=":material/slideshow:", url_path="reviews"),
        st.Page(modules.planned("actions"), title="Actions & Alerts", icon=":material/task_alt:", url_path="actions"),
    ],
    "Configuration": [
        _page(modules.org_preview, "Organization Setup", ":material/account_tree:", "organization"),
        _page(modules.kpi_preview, "KPI Studio", ":material/tune:", "kpi-studio"),
        st.Page(modules.planned("data"), title="Data Hub", icon=":material/upload_file:", url_path="data-hub"),
    ],
    "Administration": [
        st.Page(modules.planned("admin"), title="Admin & Security", icon=":material/admin_panel_settings:", url_path="admin"),
    ],
}
nav = st.navigation(pages)

with st.sidebar:
    st.markdown(f"<div style='font-size:.78rem;color:#94A3B8;margin-top:-6px'>{config.TAGLINE}</div>",
                unsafe_allow_html=True)
    st.divider()
    st.markdown(f"**{ctx.org_name}**")
    st.caption(f"Signed in as {ctx.user.get('full_name') or ctx.user['email']} · {ctx.role.title()}")
    if config.is_demo_database():
        st.caption(":material/science: Demo database · synthetic data")
    else:
        st.caption(":material/cloud_done: Connected to PostgreSQL")
    a = ai.status()
    st.caption(f":material/auto_awesome: AI: {'Gemini · ' + a.model if a.enabled else 'off'}")
    st.caption(f"v{config.VERSION}")

nav.run()
