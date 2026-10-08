"""Reusable UI building blocks.  All customer-supplied text is HTML-escaped."""
from __future__ import annotations

from html import escape

import streamlit as st

from opspulse.ui.theme import RAG, RAG_SOLID


def esc(v) -> str:
    return escape("" if v is None else str(v))


def rag_pill(status: str, text: str | None = None) -> str:
    fg, bg, label = RAG.get(status, RAG["no_data"])
    return f'<span class="op-rag" style="color:{fg};background:{bg}">{esc(text or label)}</span>'


def chip(text: str, kind: str) -> str:
    return f'<span class="op-chip {kind}">{esc(text)}</span>'


def page_header(title: str, subtitle: str = "", chips: list[str] | None = None) -> None:
    st.markdown(
        f'<div class="op-head"><div><div class="op-title">{esc(title)}</div>'
        f'<div class="op-sub">{esc(subtitle)}</div></div>'
        f'<div style="display:flex;gap:6px;flex-wrap:wrap">{"".join(chips or [])}</div></div>',
        unsafe_allow_html=True)


def delta_html(current, previous, higher_is_better: bool = True, unit: str = "", decimals: int = 1,
               label: str = "vs last month") -> str:
    if current is None or previous is None:
        return f'<span class="op-delta flat">— {esc(label)}</span>'
    diff = round(current - previous, decimals)
    if diff == 0:
        return f'<span class="op-delta flat">• no change {esc(label)}</span>'
    good = (diff > 0) == higher_is_better
    arrow = "▲" if diff > 0 else "▼"
    return (f'<span class="op-delta {"up" if good else "down"}">{arrow} {abs(diff):,.{decimals}f}{esc(unit)}</span>'
            f'<span>{esc(label)}</span>')


def kpi_card(label: str, value_html: str, foot_html: str = "", status: str | None = None, help_text: str = "") -> None:
    bar = f'<div class="bar" style="background:{RAG_SOLID.get(status, "#1D4ED8")}"></div>' if status else \
        '<div class="bar" style="background:#1D4ED8"></div>'
    title = f' title="{esc(help_text)}"' if help_text else ""
    st.markdown(f'<div class="op-card"{title}>{bar}<div class="lbl">{esc(label)}</div>'
                f'<div class="val">{value_html}</div><div class="foot">{foot_html}</div></div>',
                unsafe_allow_html=True)


def panel_title(title: str, sub: str = "") -> None:
    st.markdown(f'<div class="op-panel-title">{esc(title)}</div>' +
                (f'<div class="op-panel-sub">{esc(sub)}</div>' if sub else ""), unsafe_allow_html=True)


def empty_state(title: str, body: str, icon: str = ":material/inbox:") -> None:
    with st.container(border=True):
        st.markdown(f"#### {icon} {title}")
        st.caption(body)
