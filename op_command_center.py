"""Module A - Executive Command Center (functional in Phase 1, Module 1)."""
from __future__ import annotations

import io
from datetime import timedelta

import pandas as pd
import streamlit as st

import op_commentary as commentary
import op_provider as ai
import op_repository as repository
import op_facts as F
import op_kpi as K
from op_analytics import Analyzer
from op_health import INSUFFICIENT
import op_charts as charts
from op_components import (chip, delta_html, empty_state, esc, kpi_card, page_header, panel_title,
                                    rag_pill)
from op_session import Context
from op_theme import RAG

ALL = "All"
LEVEL_ICONS = {"business_unit": "Business unit", "client": "Client", "process": "Process",
               "location": "Location", "team": "Team"}


# ----------------------------------------------------------------------------- filters
def _level_label(az: Analyzer, level: str) -> str:
    return (az.settings.get("level_labels") or {}).get(level, level.replace("_", " ").title())


def _apply_pending_drill(levels: list[str]) -> None:
    """Chart clicks and Reset are applied here, before the filter widgets are drawn."""
    if st.session_state.pop("_reset", False):
        for lv in levels:
            st.session_state[f"f_{lv}"] = ALL
    drill = st.session_state.pop("_drill", None)
    if drill:
        level, name = drill
        st.session_state[f"f_{level}"] = name
        # clear anything below the drilled level
        for lv in levels[levels.index(level) + 1:]:
            st.session_state[f"f_{lv}"] = ALL


def _filters(az: Analyzer) -> tuple[dict, K.Period]:
    levels = az.h.levels
    _apply_pending_drill(levels)
    months = az.months()
    default = az.default_period()
    with st.container(border=True):
        cols = st.columns([1.1] + [1] * len(levels) + [0.75], vertical_alignment="bottom")
        labels = [p.label for p in months]
        if st.session_state.get("f_period") not in labels:
            st.session_state.f_period = default.label
        label = cols[0].selectbox("Reporting month", labels, key="f_period",
                                  help="Monthly view. Daily and weekly data are rolled up with each KPI's own rule.")
        period = months[labels.index(label)]
        chosen: dict[str, str | None] = {}
        for i, lv in enumerate(levels):
            opts = az.h.options(lv, chosen)
            key = f"f_{lv}"
            if st.session_state.get(key) not in opts:
                st.session_state[key] = ALL
            picked = cols[i + 1].selectbox(_level_label(az, lv), [ALL] + opts, key=key)
            chosen[lv] = None if picked == ALL else picked
        if cols[-1].button("Reset", icon=":material/restart_alt:", width="stretch",
                           help="Back to the whole organisation"):
            st.session_state["_reset"] = True
            st.rerun()
    return chosen, period


# ----------------------------------------------------------------------------- cards
def _cards(az: Analyzer, scope, period, res, prev) -> None:
    c = st.columns(5)
    with c[0]:
        val = "—" if res.score is None else f"{res.score:.1f}<small> /100</small>"
        kpi_card("Operational health", val,
                 rag_pill(res.status) + delta_html(res.score, prev.score, True, " pts"),
                 res.status, "Weighted RAG points. See 'How the health score is calculated' below.")
    with c[1]:
        procs = len(az._values("process", dict(scope.filters))) if "process" in az.h.levels else 0
        locs = len(az._values("location", dict(scope.filters))) if "location" in az.h.levels else 0
        sites = az._site_count(scope) if scope.filters else sum(1 for u in az.h.type.values() if u == az.site_level())
        kpi_card("Processes · Locations", f"{procs}<small> · </small>{locs}",
                 f"<span>{sites} process sites · {len(scope.leaf_ids)} teams</span>")
    with c[2]:
        n = len(res.scored)
        pct = f"{res.met / n:.0%}" if n else "—"
        kpi_card("KPIs meeting target", f"{res.met}<small> of {n}</small>",
                 f"<span>Combined result for the selection · {pct} · last month {prev.met} of {len(prev.scored)}</span>",
                 "green" if n and res.met == n else "amber" if n and res.met >= n * 0.7 else "red" if n else None)
    with c[3]:
        alerts = az.critical_alerts(scope, period)
        prev_alerts = az.critical_alerts(scope, period.previous_month())
        kpi_card("Critical alerts", f"{alerts}",
                 delta_html(alerts, prev_alerts, False, "", 0) +
                 "<span>Red KPIs at process-site level</span>", "red" if alerts else "green")
    with c[4]:
        cov = res.coverage
        status = "insufficient" if cov is not None and cov < az.rules["min_coverage"] else \
            ("amber" if cov is not None and cov < 0.95 else "green")
        kpi_card("Data coverage", "—" if cov is None else f"{cov:.0%}",
                 f"<span>Due observations received · as of {az.as_of:%d %b %Y}</span>", status,
                 "Missing data is not counted as poor performance; it lowers coverage instead.")


# ----------------------------------------------------------------------------- scorecard
def _scorecard_frame(az: Analyzer, res) -> pd.DataFrame:
    rows = []
    for k in res.kpis:
        var = None
        if k.actual is not None and k.target is not None:
            var = k.actual - k.target
        rows.append({
            "KPI": k.name, "Status": RAG.get(k.rag, RAG["no_data"])[2],
            "Actual": K.format_value(k.actual, k.unit, k.decimals, az.currency),
            "Target": K.format_value(k.target, k.unit, k.decimals, az.currency),
            "Variance": "—" if var is None else f"{var:+,.{k.decimals}f}",
            "Last month": K.format_value(k.previous, k.unit, k.decimals, az.currency),
            "Change": {"improved": "▲ Better", "worsened": "▼ Worse", "unchanged": "= Same"}.get(
                F._direction_word(k), "—"),
            "Data received": k.coverage if k.coverage is not None else None,
            "Weight": k.weight, "_rag": k.rag, "Frequency": k.frequency,
            "Better when": "Higher" if k.direction == "higher_better" else "Lower",
        })
    return pd.DataFrame(rows)


def _style_status(df: pd.DataFrame):
    colours = {v[2]: (v[0], v[1]) for v in RAG.values()}
    trend_c = {"improved": "#15803D", "worsened": "#B91C1C"}

    def s(col):
        if col.name == "Status":
            return [f"color:{colours.get(v, ('#475569', '#F1F5F9'))[0]};background-color:"
                    f"{colours.get(v, ('#475569', '#F1F5F9'))[1]};font-weight:600" for v in col]
        if col.name == "Change":
            return [f"color:{trend_c.get('improved' if v.startswith('▲') else 'worsened' if v.startswith('▼') else '', '#64748B')};"
                    "font-weight:600" for v in col]
        return [""] * len(col)
    return df.style.apply(s)


def _excel(az: Analyzer, scope, period, score_df: pd.DataFrame, facts: dict, sites: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        about = pd.DataFrame({"Item": ["Organisation", "Selection", "Period", "Data as of", "Data label",
                                       "Health score", "Health rule"],
                              "Value": [facts["organisation"], scope.label, period.label, str(az.as_of),
                                        facts["data_label"], facts["health_score"], facts["health_rule"]]})
        about.to_excel(xw, sheet_name="About", index=False)
        score_df.drop(columns=["_rag"]).to_excel(xw, sheet_name="KPI scorecard", index=False)
        if not sites.empty:
            sites.to_excel(xw, sheet_name="Comparison", index=False)
        pd.DataFrame({"Verified fact": F.sentences(facts)}).to_excel(xw, sheet_name="Verified facts", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(60, max(12, max(len(str(c.value or "")) for c in col) + 2))
    return buf.getvalue()


# ----------------------------------------------------------------------------- AI panel
def _ai_panel(ctx: Context, facts: dict, scope, period) -> None:
    status = ai.status()
    key = ("ai", ctx.org_id, scope.label, period.label)
    st.markdown('<div class="op-ai"><h4>✦ AI executive summary</h4>'
                '<div style="font-size:.8rem;color:#64748B">AI-generated commentary from the verified facts only. '
                'Possible explanations are hypotheses, not confirmed root causes. Review before sharing.</div></div>',
                unsafe_allow_html=True)
    if not status.enabled:
        st.markdown(f'<div class="op-ai" style="margin-top:8px"><div class="sec">Status</div>'
                    f'<div style="font-size:.88rem">AI commentary is off – {esc(status.reason)} '
                    f'Every KPI and verified fact on this page works without it. To switch it on, add '
                    f'<code>GEMINI_API_KEY</code> in Streamlit Secrets (see README).</div></div>',
                    unsafe_allow_html=True)
        return
    cached = st.session_state.get("ai_cache", {}).get(key)
    label = "Regenerate" if cached else "Generate AI summary"
    if st.button(label, icon=":material/auto_awesome:", key=f"ai_btn_{scope.label}_{period.label}",
                 type="secondary" if cached else "primary"):
        with st.spinner("Asking Gemini to summarise the verified facts…"):
            try:
                out = commentary.executive_summary(facts)
                st.session_state.setdefault("ai_cache", {})[key] = out
                cached = out
                try:
                    repository.save_ai_insight(
                        ctx.engine, ctx.org_id, unit_id=scope.anchor_id, period_start=period.start,
                        period_end=period.end, question="Executive summary", facts=facts,
                        explanations="\n".join(e["text"] for e in out["possible_explanations"]),
                        recommendations="\n".join(r["action"] for r in out["recommendations"]),
                        provider=out["provider"], model=out["model"], user_id=ctx.user["id"])
                    repository.audit(ctx.engine, ctx.org_id, ctx.user["id"], "ai_summary", "ai_insights",
                                     None, {"selection": scope.label, "period": period.label})
                except Exception:      # saving history must never block the summary
                    pass
            except ai.AIError as e:
                st.warning(str(e), icon=":material/cloud_off:")
    if not cached:
        st.caption(f"Model: {status.model}. Free Gemini keys may let Google use prompts to improve its products – "
                   "use a paid key before loading real customer data.")
        return
    with st.container(border=True):
        if cached["headline"]:
            st.markdown(f"**{cached['headline']}**")
        st.markdown('<div class="op-ai"><div class="sec">Confirmed facts</div></div>', unsafe_allow_html=True)
        for f in cached["confirmed_facts"]:
            st.markdown(f"- {f}")
        if cached["unverified_numbers"]:
            st.warning("Check before sharing: these numbers in the AI text were not found in the verified facts: "
                       + ", ".join(f"{n:g}" for n in cached["unverified_numbers"]), icon=":material/fact_check:")
        st.markdown('<div class="op-ai"><div class="sec">Possible explanations (hypotheses)</div></div>',
                    unsafe_allow_html=True)
        if cached["possible_explanations"]:
            for e in cached["possible_explanations"]:
                sup = f" _(supporting: {'; '.join(e['supporting_metrics'])})_" if e["supporting_metrics"] else ""
                st.markdown(f"- {e['text']}{sup}")
        else:
            st.caption("The data does not point to an explanation.")
        st.markdown('<div class="op-ai"><div class="sec">Recommended leadership actions</div></div>',
                    unsafe_allow_html=True)
        for r in cached["recommendations"]:
            tag = " · ".join(x for x in (r["kpi"], r["where"]) if x)
            st.markdown(f"- {r['action']}" + (f" _({tag})_" if tag else ""))
        st.caption(f"Generated by {cached['provider'].title()} ({cached['model']}). Saved to AI insight history.")


# ----------------------------------------------------------------------------- KPI drill-down
def _kpi_drill(az: Analyzer, scope, period, res) -> None:
    panel_title("KPI drill-down", "Official KPI calculation over time, and how each part of the selection compares.")
    measured = [k for k in res.kpis]
    if not measured:
        st.caption("No KPIs are assigned to this selection.")
        return
    c1, c2 = st.columns([2, 1.3])
    names = {k.kpi_id: k.name for k in measured}
    kid = c1.selectbox("KPI", list(names), format_func=names.get, key="drill_kpi")
    k = next(x for x in measured if x.kpi_id == kid)
    grans = ["day", "week", "month"] if k.frequency == "daily" else (["week", "month"] if k.frequency == "weekly" else ["month"])
    gran = c2.segmented_control("View by", grans, default="week" if "week" in grans else "month",
                                format_func=lambda g: {"day": "Daily", "week": "Weekly", "month": "Monthly"}[g],
                                key=f"drill_gran_{k.frequency}") or grans[-1]
    first = az.first
    start = first if gran == "month" else max(first, period.start - timedelta(days=(90 if gran == "week" else 30)))
    series = az.kpi_series(scope, kid, gran, start, period.end)
    left, right = st.columns([1.5, 1])
    suffix = "%" if k.unit == "percent" else ""
    with left:
        if series.empty:
            empty_state("No data for this KPI", "Nothing has been recorded for this selection and period.")
        else:
            st.plotly_chart(charts.kpi_trend(series, k.name, k.decimals, suffix), width="stretch",
                            config={"displayModeBar": False}, key=f"kpitrend_{kid}_{gran}_{scope.label}")
            st.caption(f"Calculation: {az.kpis.loc[kid, 'numerator_label'] or 'value'} ÷ "
                       f"{az.kpis.loc[kid, 'denominator_label'] or '1'} × {az.kpis.loc[kid, 'multiplier']:g} · "
                       f"aggregation: {az.kpis.loc[kid, 'aggregation'].replace('_', ' ')} · "
                       f"{'higher' if k.direction == 'higher_better' else 'lower'} is better · "
                       f"Green {'≥' if k.direction == 'higher_better' else '≤'} {k.green:g}, "
                       f"Amber {'≥' if k.direction == 'higher_better' else '≤'} {k.amber:g}"
                       if k.green is not None else "No target set")
    with right:
        level = az.child_level(scope)
        if not level:
            st.caption("This is the lowest level – nothing further to compare.")
            return
        rows = []
        for name in az.h.options(level, dict(scope.filters)):
            sub = az.h.scope({**dict(scope.filters), level: name})
            r = az.evaluate(sub, period, with_previous=False)
            kk = next((x for x in r.kpis if x.kpi_id == kid), None)
            if kk:
                rows.append({"name": name, "actual": kk.actual, "rag": kk.rag})
        if rows:
            st.markdown(f"**{k.name} by {_level_label(az, level).lower()}** · {period.label}")
            st.plotly_chart(charts.kpi_by_group(pd.DataFrame(rows), k.target, k.decimals), width="stretch",
                            config={"displayModeBar": False}, key=f"kpibygroup_{kid}_{scope.label}")


# ----------------------------------------------------------------------------- page
def render(ctx: Context) -> None:
    az = ctx.analyzer
    synthetic = bool(az.bundle.org.get("is_demo"))
    if az.as_of is None:
        page_header("Executive Command Center", ctx.org_name)
        empty_state("No approved KPI data yet", "Once data is uploaded and approved in the Data Hub, the "
                    "dashboard fills in automatically.")
        return
    page_header("Executive Command Center",
                f"{ctx.org_name} · data as of {az.as_of:%d %b %Y}",
                [chip("SYNTHETIC DEMO DATA", "synthetic") if synthetic else chip("Approved data", "live"),
                 chip("Verified KPI engine", "functional")])

    chosen, period = _filters(az)
    scope = az.h.scope(chosen)
    if not scope.leaf_ids:
        empty_state("Nothing matches this selection", "Choose 'All' for one of the filters, or press Reset.")
        return

    with st.spinner("Calculating KPIs…"):
        res = az.evaluate(scope, period)
        prev = az.evaluate(scope, period.previous_month(), with_previous=False)
        facts = F.build(az, scope, period)

    crumbs = " › ".join(["Organisation"] + [v for _, v in scope.filters])
    st.markdown(f'<div class="op-sub" style="margin:-2px 0 10px 2px">📍 <b>{esc(crumbs)}</b> · {esc(period.label)} '
                f'compared with {esc(period.previous_month().label)}</div>', unsafe_allow_html=True)
    if res.status == INSUFFICIENT:
        st.warning(f"Only {res.coverage:.0%} of the expected data has been received for this selection, so the "
                   "health score is shown as **Insufficient data**. Missing data is not treated as poor performance.",
                   icon=":material/report:")

    _cards(az, scope, period, res, prev)
    st.write("")

    # ---- trend + comparison
    level = az.child_level(scope)
    left, right = st.columns([1.25, 1])
    with left, st.container(border=True):
        panel_title("Operational health trend", "Monthly health score with Green / Amber / Red bands")
        months = [p for p in az.months() if p.start <= period.start][-6:]
        trend = az.health_trend(scope, months)
        st.plotly_chart(charts.health_trend(trend, az.rules["bands"]), width="stretch",
                        config={"displayModeBar": False}, key=f"trend_{scope.label}_{period.label}")
    comp = pd.DataFrame()
    with right, st.container(border=True):
        if level:
            lbl = _level_label(az, level)
            panel_title(f"{lbl} comparison", f"Health by {lbl.lower()} · click a bar to drill down")
            comp = az.compare(scope, period, level)
            event = st.plotly_chart(charts.comparison_bars(comp), width="stretch", on_select="rerun",
                                    selection_mode="points", config={"displayModeBar": False},
                                    key=f"cmp_{scope.label}_{period.label}")
            pts = (event.get("selection") or {}).get("points") or [] if event else []
            if pts:
                name = pts[0].get("y")
                if name:
                    st.session_state["_drill"] = (level, name)
                    st.rerun()
        else:
            panel_title("Lowest level reached", "Use the KPI drill-down below for detail.")
            st.caption(scope.label)

    # ---- scorecard (full width)
    score_df = _scorecard_frame(az, res)
    with st.container(border=True):
        panel_title("KPI scorecard", f"{scope.label} · {period.label} · official calculation from approved data")
        if score_df.empty:
            st.caption("No KPIs assigned.")
        else:
            show = score_df.drop(columns=["_rag", "Frequency", "Better when", "Weight"])
            st.dataframe(_style_status(show), hide_index=True, width="stretch",
                         column_config={
                             "Data received": st.column_config.ProgressColumn(
                                 "Data received", min_value=0, max_value=1, format="percent",
                                 help="Share of due observations received for this KPI"),
                             "KPI": st.column_config.TextColumn("KPI", width="medium")})

    # ---- heat map + risks
    mat = pd.DataFrame()
    if "process" in az.h.levels and "location" in az.h.levels:
        mat = az.matrix(scope, period, "process", "location")
    show_map = not mat.empty and mat["process"].nunique() > 1 and mat["location"].nunique() > 1
    left, right = st.columns([1.4, 1]) if show_map else (None, st.container())
    if show_map:
        with left, st.container(border=True):
            panel_title("Process × location health map", f"{period.label} · each cell is one process site")
            st.plotly_chart(charts.heatmap(mat, "process", "location"), width="stretch",
                            config={"displayModeBar": False}, key=f"heat_{scope.label}_{period.label}")
    with right, st.container(border=True):
        panel_title("Top operational risks", "Red KPIs ranked by weight × gap to target; data gaps listed after")
        risks = az.risks(scope, period, limit=6)
        if not risks:
            st.success("No red KPIs or data gaps in this selection.", icon=":material/verified:")
        for r in risks:
            cls = "op-risk gap" if r.kind == "data_gap" else "op-risk"
            tag = "Data gap" if r.kind == "data_gap" else "Critical"
            st.markdown(f'<div class="{cls}"><div class="t">{esc(r.kpi_name)} · {esc(r.scope_label)}</div>'
                        f'<div class="d">{esc(tag)} – {esc(r.detail)}</div></div>', unsafe_allow_html=True)

    # ---- verified facts + AI
    left, right = st.columns(2)
    with left:
        items = "".join(f"<li>{esc(s)}</li>" for s in F.sentences(facts))
        st.markdown(f'<div class="op-verified"><h4>✓ Verified facts</h4>'
                    f'<div style="font-size:.8rem;color:#64748B;margin-bottom:6px">Calculated by the KPI engine from '
                    f'approved data – no AI involved.</div><ul class="op-facts">{items}</ul></div>',
                    unsafe_allow_html=True)
    with right:
        _ai_panel(ctx, facts, scope, period)

    # ---- methodology
    with st.expander("How the health score is calculated", icon=":material/calculate:"):
        pts = az.rules["points"]
        st.markdown(
            f"**Site score** = Σ(KPI weight × RAG points) ÷ Σ(weights of KPIs with data). "
            f"Points: Green **{pts['green']:.0f}**, Amber **{pts['amber']:.0f}**, Red **{pts['red']:.0f}**. "
            f"KPIs without data are excluded and reduce **data coverage** instead of the score. "
            f"Status: ≥ {az.rules['bands']['green']:.0f} Green, ≥ {az.rules['bands']['amber']:.0f} Amber, "
            f"otherwise Red; below {az.rules['min_coverage']:.0%} coverage the status is *Insufficient data*.")
        if res.rollup == "sites":
            st.markdown(f"This selection spans **{len(res.components)} process sites**, so its score is the simple "
                        "average of the site scores (sites with insufficient data are left out and shown below). "
                        "This stops a failing site from being hidden by large, healthy sites.")
            comp_df = pd.DataFrame(res.components).rename(columns={"label": "Site", "score": "Score",
                                                                  "status": "Status", "coverage": "Data coverage"})
            comp_df["Status"] = comp_df["Status"].map(lambda s: RAG.get(s, RAG["no_data"])[2])
            st.dataframe(comp_df.sort_values("Score"), hide_index=True, width="stretch",
                         column_config={"Data coverage": st.column_config.ProgressColumn(
                             min_value=0, max_value=1, format="percent")})
        else:
            br = pd.DataFrame([{"KPI": k.name, "Weight": k.weight, "Status": RAG.get(k.rag, RAG["no_data"])[2],
                                "Points": k.points, "Contribution": (k.weight * k.points) if k.points is not None else None}
                               for k in res.kpis])
            st.dataframe(br, hide_index=True, width="stretch")
            scored_w = sum(k.weight for k in res.scored)
            if scored_w:
                st.caption(f"Score = {sum(k.weight * k.points for k in res.scored):,.0f} ÷ {scored_w:,.0f} = "
                           f"**{res.score:.1f}**")

    # ---- drill-down
    with st.container(border=True):
        _kpi_drill(az, scope, period, res)

    # ---- export
    c1, c2 = st.columns([1, 3])
    data = _excel(az, scope, period, score_df, facts, comp)
    if c1.download_button("Export to Excel", data, file_name=f"OpsPulse_{period.start:%Y-%m}_scorecard.xlsx",
                          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                          icon=":material/download:", width="stretch"):
        repository.audit(ctx.engine, ctx.org_id, ctx.user["id"], "export", "scorecard", None,
                         {"selection": scope.label, "period": period.label})
    c2.caption("Exports contain the verified scorecard, comparison and facts for the current selection. "
               + ("All figures are synthetic demonstration data." if synthetic else ""))
