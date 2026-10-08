"""Screens for modules that are not built yet (clearly labelled as PLANNED),
plus read-only previews of the organisation hierarchy and KPI catalogue."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import op_kpi as K
from op_components import chip, esc, page_header, panel_title
from op_session import Context

MODULES = {
    "org": dict(letter="B", title="Organization Setup", icon=":material/account_tree:", phase="Phase 1 · Module 2",
                purpose="Administrators configure Organisation → Business Unit → Client/Account → Process → Location → "
                        "Team, invite users, assign roles and grant process-level access.",
                screens=[("Hierarchy builder", "Tree with add / rename / move / deactivate, custom level names"),
                         ("Users & roles", "Invite by e-mail, role = Owner / Admin / Analyst / Manager / Viewer"),
                         ("Access matrix", "Grant view / edit / approve on any unit – applies to everything below it"),
                         ("Change history", "Every change written to the audit log")]),
    "kpi": dict(letter="C", title="KPI Studio", icon=":material/tune:", phase="Phase 1 · Module 3",
                purpose="No-code KPI builder: name, unit, numerator/denominator, direction, frequency, aggregation, "
                        "targets and RAG thresholds with effective dates, KPI owner and weight.",
                screens=[("KPI library", "Search, filter, duplicate, retire KPIs; templates for SLA, AHT, CSAT …"),
                         ("KPI builder", "Step-by-step form with live preview of the calculation on sample data"),
                         ("Targets & thresholds", "Organisation default plus overrides per process / location"),
                         ("Assignments", "Which KPIs apply to which units, and their health-score weights")]),
    "data": dict(letter="D", title="Data Hub", icon=":material/upload_file:", phase="Phase 1 · Module 4",
                 purpose="Manual entry and Excel/CSV upload with validation, duplicate detection, missing-data alerts, "
                         "error correction and an approval workflow. Original files and every change are retained.",
                 screens=[("Upload wizard", "Download template → upload → column mapping → validation report"),
                          ("Validation results", "Accepted / rejected rows with reasons, fix-and-resubmit"),
                          ("Approval queue", "Approvers release submitted data into official KPI results"),
                          ("Missing data monitor", "Expected vs received observations per unit and KPI")]),
    "analytics": dict(letter="E", title="Process Analytics", icon=":material/monitoring:", phase="Phase 1 · Module 5",
                      purpose="Interactive scorecards, actual vs target, daily/weekly/monthly trends, process and "
                              "location comparisons, variance and exception reports, history and forecasting.",
                      screens=[("Scorecard explorer", "Any unit, any period, any KPI set"),
                               ("Variance analysis", "Contribution of each site / team to the movement"),
                               ("Exception report", "All red / deteriorating KPIs with export"),
                               ("Forecast", "Shown only when at least 12 data points exist, with confidence band")]),
    "ai": dict(letter="F", title="AI Operations Analyst", icon=":material/psychology:", phase="Phase 1 · Module 6",
               purpose="Ask questions such as “Why did SLA decline?” or “Which KPIs are likely to miss target?”. "
                       "Answers use only authorised, verified data and are split into confirmed facts, possible "
                       "explanations and recommendations, with the supporting metrics shown.",
               screens=[("Ask the analyst", "Chat with suggested questions; scope follows the user's access rights"),
                        ("Evidence panel", "Every answer lists the exact KPI results it used"),
                        ("Insight history", "Saved answers with model, prompt facts and timestamp"),
                        ("Provider settings", "Gemini today; architecture ready for other providers")]),
    "ppt": dict(letter="G", title="PowerPoint Review Studio", icon=":material/slideshow:", phase="Phase 1 · Module 7",
                purpose="Upload a branded PPTX template, choose review type, process, location, period, KPIs and "
                        "sections, generate charts, tables and AI commentary, preview, approve and download an "
                        "editable PPTX (python-pptx).",
                screens=[("Template library", "Upload template, map placeholders to slide types once"),
                         ("Review builder", "Weekly / monthly / quarterly / executive, KPI and section picker"),
                         ("Preview & approve", "Slide thumbnails, edit commentary, approval stamp"),
                         ("Download", "Fully editable .pptx with native charts and tables")]),
    "actions": dict(letter="H", title="Actions & Alerts", icon=":material/task_alt:", phase="Phase 2",
                    purpose="Corrective actions linked to process and KPI, with owner, priority, due date, status, "
                            "escalation, closure evidence and overdue reporting; alert rules for red KPIs and data gaps.",
                    screens=[("Action board", "Kanban and list views, filters by owner / process / priority"),
                             ("Action detail", "History, comments, evidence upload, escalation level 0–3"),
                             ("Alert rules", "Red KPI, deterioration for N periods, missing data"),
                             ("Overdue report", "Overdue by owner and process, exportable")]),
    "mobile": dict(letter="I", title="Leadership Mobile", icon=":material/smartphone:", phase="Phase 2",
                   purpose="A fast phone view: pick a process and immediately see health, KPI exceptions, trend, "
                           "critical risks, open actions and the AI summary. The Command Center already adapts to "
                           "narrow screens; the dedicated mobile layout and installable web app come in Phase 2.",
                   screens=[("Process picker", "Favourites first, one tap"),
                            ("Health card", "Score, status, change vs last month"),
                            ("Exceptions", "Only red/amber KPIs, swipe for trend"),
                            ("Actions", "Open and overdue actions for that process")]),
    "admin": dict(letter="J", title="Admin & Security", icon=":material/admin_panel_settings:", phase="Phase 2",
                  purpose="Multi-tenant separation, role-based access, sign-in, audit logs, secrets management, "
                          "export controls, organisation settings, template management, backup and recovery.",
                  screens=[("Sign-in", "Supabase Auth (e-mail / magic link), enterprise SSO in Phase 3"),
                           ("Audit log", "Who changed what and when – append-only"),
                           ("Organisation settings", "Health-score points, bands, coverage rule, branding"),
                           ("Data controls", "Export permissions, retention, backup status")]),
}


def planned(key: str):
    spec = MODULES[key]

    def page() -> None:
        page_header(f"{spec['title']}", f"Module {spec['letter']} · {spec['phase']}",
                    [chip("PLANNED – not built yet", "planned")])
        st.info("This screen is a design preview only. None of the controls below are functional yet; it shows what "
                "this module will contain when it is built.", icon=":material/construction:")
        with st.container(border=True):
            panel_title("Purpose")
            st.write(spec["purpose"])
        panel_title("Screen design", "Planned layout")
        cols = st.columns(2)
        for i, (name, desc) in enumerate(spec["screens"]):
            cols[i % 2].markdown(f'<div class="op-wire"><b>{esc(name)}</b><br>{esc(desc)}</div>',
                                 unsafe_allow_html=True)
            cols[i % 2].write("")
    page.__name__ = f"planned_{key}"
    return page


def org_preview(ctx: Context) -> None:
    az = ctx.analyzer
    page_header("Organization Setup", "Module B · read-only preview of the configured hierarchy",
                [chip("Read-only now · editing in Module 2", "planned")])
    t = az.h.unit_table()
    levels = az.h.levels
    labels = (az.settings.get("level_labels") or {})
    c = st.columns(len(levels))
    for i, lv in enumerate(levels):
        c[i].metric(labels.get(lv, lv.title()), int((t["unit_type"] == lv).sum()))
    with st.container(border=True):
        panel_title("Hierarchy", "Organisation → " + " → ".join(labels.get(lv, lv) for lv in levels))
        leaves = t[t["is_leaf"]][levels].rename(columns=labels).sort_values([labels.get(lv, lv) for lv in levels])
        st.dataframe(leaves, hide_index=True, width="stretch", height=420)
    st.caption("Roles available: Owner, Admin, Analyst (all units), Manager and Viewer (only granted units). "
               "Database-level enforcement is defined in supabase/migrations/0002_rls.sql.")


def kpi_preview(ctx: Context) -> None:
    az = ctx.analyzer
    page_header("KPI Studio", "Module C · read-only KPI catalogue", [chip("Read-only now · builder in Module 3", "planned")])
    k = az.kpis.copy()
    period = az.default_period()
    rows = []
    for r in k.itertuples():
        t = az.target_for(r.id, None, period.end) if period else None
        rows.append({
            "Code": r.code, "KPI": r.name, "Unit": r.unit,
            "Calculation": f"{r.numerator_label} ÷ {r.denominator_label} × {r.multiplier:g}" if r.calc_type == "ratio"
            else "Entered value",
            "Better when": "Higher" if r.direction == "higher_better" else "Lower",
            "Frequency": r.frequency.title(), "Aggregation": r.aggregation.replace("_", " "),
            "Target (default)": K.format_value(t["target"], r.unit, r.decimals, az.currency) if t else "—",
            "Green": t["green_threshold"] if t else None, "Amber": t["amber_threshold"] if t else None,
            "Description": r.description})
    with st.container(border=True):
        panel_title("KPI definitions", "Only fixed, safe calculation types are allowed – no user formulas are executed")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    a = az.bundle.assignments.merge(az.bundle.kpis[["id", "code"]], left_on="kpi_id", right_on="id")
    a["unit"] = a["unit_id"].map(az.h.name)
    with st.container(border=True):
        panel_title("Health-score weights by process")
        pv = a.pivot_table(index="unit", columns="code", values="weight", aggfunc="first")
        pv.index.name = "Process"
        st.dataframe(pv.map(lambda v: "—" if pd.isna(v) else f"{v:g}"), width="stretch")
        st.caption("— = KPI not measured for that process.")
