"""Design tokens and global styling for OpsPulse AI."""
from __future__ import annotations

import streamlit as st

NAVY = "#0B1F3A"
BLUE = "#1D4ED8"
SKY = "#0EA5E9"
PURPLE = "#6D28D9"          # reserved for AI-generated content only
INK = "#0F172A"
MUTED = "#64748B"
LINE = "#E2E8F0"
BG = "#F4F6FB"

RAG = {   # status -> (text colour, background, label)
    "green": ("#15803D", "#DCFCE7", "On track"),
    "amber": ("#B45309", "#FEF3C7", "At risk"),
    "red": ("#B91C1C", "#FEE2E2", "Critical"),
    "insufficient": ("#475569", "#E2E8F0", "Insufficient data"),
    "no_data": ("#475569", "#F1F5F9", "No data"),
    "not_due": ("#475569", "#F1F5F9", "Not yet due"),
}
RAG_SOLID = {"green": "#16A34A", "amber": "#F59E0B", "red": "#DC2626",
             "insufficient": "#94A3B8", "no_data": "#CBD5E1", "not_due": "#CBD5E1"}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input, select, textarea {{
  font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
}}
.block-container {{ padding-top: 3.4rem; padding-bottom: 3rem; max-width: 1480px; }}
h1, h2, h3 {{ letter-spacing: -0.01em; color: {INK}; }}
/* navy sidebar even if .streamlit/config.toml is missing */
[data-testid="stSidebar"] {{ background-color: {NAVY}; }}
[data-testid="stSidebar"] .stMarkdown p, [data-testid="stSidebar"] label {{ color: #CBD5E1; }}
[data-testid="stSidebarNav"] a span, [data-testid="stSidebarNav"] span, [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{ color: #E2E8F0; }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{ background-color: #1E3A5F; }}
[data-testid="stSidebarNav"] a span {{ font-weight: 500; }}

/* page header */
.op-head {{ display:flex; align-items:flex-end; justify-content:space-between; gap:16px; flex-wrap:wrap;
  margin: 0 0 .6rem 0; }}
.op-title {{ font-size: 1.7rem; font-weight: 700; color:{INK}; margin:0; line-height:1.2; }}
.op-sub {{ color:{MUTED}; font-size: .9rem; margin-top: 2px; }}
.op-chip {{ display:inline-flex; align-items:center; gap:6px; padding:3px 10px; border-radius:999px;
  font-size:.75rem; font-weight:600; border:1px solid transparent; white-space:nowrap; }}
.op-chip.synthetic {{ background:#FFF7ED; color:#9A3412; border-color:#FED7AA; }}
.op-chip.live {{ background:#ECFDF5; color:#047857; border-color:#A7F3D0; }}
.op-chip.planned {{ background:#EEF2FF; color:#3730A3; border-color:#C7D2FE; }}
.op-chip.functional {{ background:#ECFDF5; color:#047857; border-color:#A7F3D0; }}
.op-chip.ai {{ background:#F5F3FF; color:{PURPLE}; border-color:#DDD6FE; }}

/* KPI cards */
.op-card {{ background:#fff; border:1px solid {LINE}; border-radius:14px; padding:16px 18px;
  box-shadow: 0 1px 2px rgba(15,23,42,.04); min-height:172px; position:relative; overflow:hidden; }}
.op-card .lbl {{ color:{MUTED}; font-size:.78rem; font-weight:600; text-transform:uppercase; letter-spacing:.04em; }}
.op-card .val {{ font-size:2rem; font-weight:700; color:{INK}; line-height:1.15; margin-top:6px; }}
.op-card .val small {{ font-size:1rem; color:{MUTED}; font-weight:600; }}
.op-card .foot {{ font-size:.8rem; color:{MUTED}; margin-top:6px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
.op-card .bar {{ position:absolute; left:0; top:0; bottom:0; width:4px; }}
.op-delta.up {{ color:#15803D; font-weight:600; }}
.op-delta.down {{ color:#B91C1C; font-weight:600; }}
.op-delta.flat {{ color:{MUTED}; font-weight:600; }}

/* RAG pill */
.op-rag {{ display:inline-block; padding:2px 9px; border-radius:999px; font-size:.72rem; font-weight:700; }}

/* panels */
.op-panel-title {{ font-weight:700; color:{INK}; font-size:1rem; margin:0 0 2px 0; }}
.op-panel-sub {{ color:{MUTED}; font-size:.8rem; margin:0 0 8px 0; line-height:1.35; }}
.op-facts li {{ margin-bottom:6px; color:{INK}; font-size:.9rem; }}
.op-risk {{ border:1px solid {LINE}; border-left:4px solid #DC2626; border-radius:10px; padding:9px 12px;
  margin-bottom:8px; background:#fff; }}
.op-risk.gap {{ border-left-color:#94A3B8; }}
.op-risk .t {{ font-weight:600; font-size:.88rem; color:{INK}; }}
.op-risk .d {{ font-size:.8rem; color:{MUTED}; }}

/* AI area - always purple-accented so it is never confused with verified numbers */
.op-ai {{ border:1px solid #DDD6FE; background:linear-gradient(180deg,#FAF8FF 0,#FFFFFF 60%);
  border-radius:14px; padding:16px 18px; }}
.op-ai h4 {{ margin:0 0 6px 0; color:{PURPLE}; font-size:.95rem; }}
.op-ai .sec {{ font-size:.75rem; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:{MUTED}; margin-top:10px; }}
.op-verified {{ border:1px solid #BFDBFE; background:#F8FBFF; border-radius:14px; padding:16px 18px; }}
.op-verified h4 {{ margin:0 0 6px 0; color:{BLUE}; font-size:.95rem; }}

/* planned module pages */
.op-wire {{ border:1.5px dashed #CBD5E1; border-radius:12px; padding:14px; background:#fff; color:{MUTED};
  font-size:.85rem; min-height:90px; }}
.op-wire b {{ color:{INK}; }}

/* small screens: tighter cards */
@media (max-width: 640px) {{
  .op-card .val {{ font-size:1.6rem; }}
  .op-title {{ font-size:1.25rem; }}
  .block-container {{ padding-left: .8rem; padding-right: .8rem; padding-top: 3.2rem; }}
  .op-card {{ min-height: 0; }}
}}
div[data-testid="stExpander"] details {{ background:#fff; border-radius:12px; }}
div[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="stVerticalBlock"] {{ gap: .6rem; }}
</style>
"""


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
