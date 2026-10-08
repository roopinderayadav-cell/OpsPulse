"""Plotly chart builders with the OpsPulse look."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from op_theme import BLUE, INK, LINE, MUTED, RAG_SOLID

STATUS_NAME = {"green": "On track", "amber": "At risk", "red": "Critical",
               "insufficient": "Insufficient data", "no_data": "No data", "not_due": "Not yet due"}


def _layout(fig: go.Figure, height: int = 300) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Inter, Segoe UI, sans-serif", color=INK, size=12),
                      hoverlabel=dict(bgcolor="white", font_size=12), showlegend=False)
    fig.update_xaxes(showgrid=False, linecolor=LINE, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor="#EEF2F7", zeroline=False, tickfont=dict(color=MUTED))
    return fig


def health_trend(df: pd.DataFrame, bands: dict) -> go.Figure:
    fig = go.Figure()
    g, a = bands["green"], bands["amber"]
    lo = max(0, min([v for v in df["score"].dropna()] + [a]) - 10)
    fig.add_hrect(y0=g, y1=101, fillcolor="#DCFCE7", opacity=0.45, line_width=0)
    fig.add_hrect(y0=a, y1=g, fillcolor="#FEF3C7", opacity=0.45, line_width=0)
    fig.add_hrect(y0=lo, y1=a, fillcolor="#FEE2E2", opacity=0.45, line_width=0)
    colors = [RAG_SOLID.get(s, "#94A3B8") for s in df["status"]]
    fig.add_trace(go.Scatter(
        x=df["period"], y=df["score"], mode="lines+markers+text", line=dict(color=BLUE, width=3, shape="spline"),
        marker=dict(size=11, color=colors, line=dict(color="white", width=2)),
        text=[f"{v:.1f}" if pd.notna(v) else "" for v in df["score"]], textposition="top center",
        textfont=dict(size=11, color=INK),
        customdata=[[STATUS_NAME.get(s, s), f"{c:.0%}" if pd.notna(c) else "—"] for s, c in zip(df["status"], df["coverage"])],
        hovertemplate="<b>%{x}</b><br>Health %{y:.1f}<br>%{customdata[0]}<br>Data received %{customdata[1]}<extra></extra>"))
    fig.update_yaxes(range=[lo, 103], title=None)
    return _layout(fig, 280)


def comparison_bars(df: pd.DataFrame) -> go.Figure:
    d = df.sort_values("score", ascending=True, na_position="first")
    colors = [RAG_SOLID.get(s, "#CBD5E1") for s in d["status"]]
    labels = [f"{v:.1f}" if pd.notna(v) else "No data" for v in d["score"]]
    fig = go.Figure(go.Bar(
        x=d["score"].fillna(0), y=d["name"], orientation="h", marker=dict(color=colors), text=labels,
        textposition="outside", cliponaxis=False,
        customdata=[[STATUS_NAME.get(s, s), f"{c:.0%}" if pd.notna(c) else "—",
                     f"{p:.1f}" if pd.notna(p) else "—"] for s, c, p in zip(d["status"], d["coverage"], d["previous"])],
        hovertemplate="<b>%{y}</b><br>Health %{x:.1f} (%{customdata[0]})<br>Previous month %{customdata[2]}"
                      "<br>Data received %{customdata[1]}<br><i>Click to drill down</i><extra></extra>"))
    fig.update_xaxes(range=[0, 112], showticklabels=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(color=INK, size=12))
    return _layout(fig, max(220, 46 * len(d) + 40))


def heatmap(df: pd.DataFrame, rows: str, cols: str) -> go.Figure:
    pv = df.pivot(index=rows, columns=cols, values="score")
    st_ = df.pivot(index=rows, columns=cols, values="status")
    z = pv.values
    text = [[(f"{v:.0f}" if pd.notna(v) else "—") + ("<br>⚠ data" if s == "insufficient" else "")
             for v, s in zip(rv, sv)] for rv, sv in zip(z, st_.values)]
    scale = [[0, "#DC2626"], [0.45, "#F87171"], [0.55, "#FBBF24"], [0.75, "#FDE68A"], [0.8, "#86EFAC"], [1, "#16A34A"]]
    fig = go.Figure(go.Heatmap(
        z=z, x=list(pv.columns), y=list(pv.index), text=text, texttemplate="%{text}", textfont=dict(size=13),
        colorscale=scale, zmin=40, zmax=100, showscale=False, xgap=4, ygap=4,
        hovertemplate="<b>%{y} · %{x}</b><br>Health %{z:.1f}<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(side="top", showgrid=False)
    return _layout(fig, 60 * len(pv.index) + 60)


def kpi_trend(df: pd.DataFrame, kpi_name: str, decimals: int, suffix: str = "") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["bucket"], y=df["target"], mode="lines", name="Target",
                             line=dict(color="#94A3B8", dash="dash", width=2), hovertemplate="Target %{y}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=df["bucket"], y=df["actual"], mode="lines+markers", name=kpi_name, line=dict(color=BLUE, width=2.5),
        marker=dict(size=7, color=[RAG_SOLID.get(s, "#94A3B8") for s in df["rag"]], line=dict(color="white", width=1)),
        hovertemplate=f"%{{x}}<br>{kpi_name} %{{y:.{decimals}f}}{suffix}<extra></extra>"))
    fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.12, x=0))
    out = _layout(fig, 300)
    out.update_layout(showlegend=True)
    return out


def kpi_by_group(df: pd.DataFrame, target: float | None, decimals: int) -> go.Figure:
    d = df.sort_values("actual")
    fig = go.Figure(go.Bar(x=d["name"], y=d["actual"], marker=dict(color=[RAG_SOLID.get(s, "#CBD5E1") for s in d["rag"]]),
                           text=[f"{v:,.{decimals}f}" if pd.notna(v) else "—" for v in d["actual"]],
                           textposition="outside", cliponaxis=False,
                           hovertemplate="%{x}<br>%{y:." + str(decimals) + "f}<extra></extra>"))
    vals = [v for v in d["actual"].dropna()] + ([target] if target is not None else [])
    if vals:
        lo, hi = min(vals), max(vals)
        pad = max((hi - lo) * 0.35, abs(hi) * 0.02, 0.01)
        fig.update_yaxes(range=[max(0, lo - pad) if lo >= 0 else lo - pad, hi + pad])
    if target is not None:
        fig.add_hline(y=target, line=dict(color="#475569", dash="dash", width=1.5),
                      annotation_text="Target", annotation_position="top left")
    return _layout(fig, 300)
