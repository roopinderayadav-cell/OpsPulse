"""Analyzer: turns approved observations into scorecards, comparisons, trends and risks.

All official numbers on the dashboard come from here (never from AI)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from op_repository import OrgBundle
import op_health as H
import op_kpi as K
from op_hierarchy import Hierarchy, Scope


@dataclass
class Risk:
    scope_label: str
    process: str | None
    location: str | None
    kpi_code: str
    kpi_name: str
    actual: float | None
    target: float | None
    previous: float | None
    rag: str
    severity: float
    kind: str          # "performance" or "data_gap"
    detail: str


class Analyzer:
    def __init__(self, bundle: OrgBundle):
        self.bundle = bundle
        self.settings = bundle.org.get("settings") or {}
        self.currency = self.settings.get("currency", "INR")
        self.rules = H.rules_from_settings(self.settings)
        self.h = Hierarchy(bundle.units, self.settings.get("hierarchy_levels"))
        self.kpis = bundle.kpis.set_index("id", drop=False)
        obs = bundle.observations.copy()
        obs["d"] = obs["period_start"].dt.date
        self.obs = obs
        self.as_of: date | None = obs["d"].max() if not obs.empty else None
        self.first: date | None = obs["d"].min() if not obs.empty else None
        self._cache: dict = {}
        self._targets: dict[str, list[dict]] = {}
        for t in bundle.targets.to_dict("records"):
            t["effective_from"] = t["effective_from"].date()
            t["effective_to"] = None if pd.isna(t["effective_to"]) else t["effective_to"].date()
            t["unit_id"] = t["unit_id"] or None
            self._targets.setdefault(t["kpi_id"], []).append(t)
        self._by_month = {k: g for k, g in obs.groupby([obs["period_start"].dt.year, obs["period_start"].dt.month])}
        self.rollup = (self.settings.get("health") or {}).get("rollup", "sites")

    # ------------------------------------------------------------------ periods
    def months(self) -> list[K.Period]:
        if self.as_of is None:
            return []
        return K.months_between(self.first, self.as_of)

    def complete_months(self) -> list[K.Period]:
        return [p for p in self.months() if p.end <= self.as_of]

    def default_period(self) -> K.Period | None:
        done = self.complete_months()
        return done[-1] if done else (self.months()[-1] if self.months() else None)

    # ------------------------------------------------------------------ assignments & targets
    def _assigned(self, scope: Scope, on: date) -> dict[str, dict]:
        """kpi_id -> {"weight": mean weight, "leaves": [leaf ids measured on this KPI]}"""
        key = ("assigned", scope.leaf_ids, on)
        if key not in self._cache:
            self._cache[key] = self._assigned_uncached(scope, on)
        return self._cache[key]

    def _assigned_uncached(self, scope: Scope, on: date) -> dict[str, dict]:
        a = self.bundle.assignments
        ts = pd.Timestamp(on)
        a = a[(a["effective_from"] <= ts) & (a["effective_to"].isna() | (a["effective_to"] >= ts))]
        by_unit: dict[str, list] = {}
        for r in a.itertuples():
            by_unit.setdefault(r.unit_id, []).append((r.kpi_id, float(r.weight)))
        out: dict[str, dict] = {}
        for leaf in scope.leaf_ids:
            seen = set()
            for anc in self.h.ancestors(leaf):          # nearest assignment wins
                for kpi_id, w in by_unit.get(anc, []):
                    if kpi_id in seen:
                        continue
                    seen.add(kpi_id)
                    d = out.setdefault(kpi_id, {"weights": [], "leaves": []})
                    d["weights"].append(w)
                    d["leaves"].append(leaf)
        return {k: {"weight": sum(v["weights"]) / len(v["weights"]), "leaves": v["leaves"]} for k, v in out.items()}

    def target_for(self, kpi_id: str, anchor_id: str | None, on: date) -> dict | None:
        """Most specific target: the unit itself, then its parents, then the organisation default."""
        key = ("target", kpi_id, anchor_id, on)
        if key not in self._cache:
            self._cache[key] = self._target_uncached(kpi_id, anchor_id, on)
        return self._cache[key]

    def _target_uncached(self, kpi_id: str, anchor_id: str | None, on: date) -> dict | None:
        live = [t for t in self._targets.get(kpi_id, [])
                if t["effective_from"] <= on and (t["effective_to"] is None or t["effective_to"] >= on)]
        if not live:
            return None
        for uid in (self.h.ancestors(anchor_id) if anchor_id else []):    # most specific unit first
            hits = [t for t in live if t["unit_id"] == uid]
            if hits:
                return max(hits, key=lambda t: t["effective_from"])
        defaults = [t for t in live if t["unit_id"] is None]
        return max(defaults, key=lambda t: t["effective_from"]) if defaults else None

    # ------------------------------------------------------------------ evaluation
    def _rows(self, scope: Scope, start: date, end: date, kpi_id: str | None = None) -> pd.DataFrame:
        o = self._by_month.get((start.year, start.month)) if (start.day == 1 and K.Period.month(
            start.year, start.month).end == end) else None
        if o is None:
            o = self.obs
        m = (o["d"] >= start) & (o["d"] <= end) & o["unit_id"].isin(scope.unit_ids)
        if kpi_id:
            m &= o["kpi_id"] == kpi_id
        return o[m]

    def evaluate(self, scope: Scope, period: K.Period, with_previous: bool = True) -> H.HealthResult:
        key = ("eval", scope.unit_ids, period, with_previous)
        if key in self._cache:
            return self._cache[key]
        rows = self._rows(scope, period.start, period.end)
        grouped = dict(tuple(rows.groupby("kpi_id"))) if not rows.empty else {}
        assigned = self._assigned(scope, period.end)
        prev = self.evaluate(scope, period.previous_month(), with_previous=False) if with_previous else None
        prev_by = {k.kpi_id: k for k in prev.kpis} if prev else {}
        results = []
        for kpi_id, info in assigned.items():
            if kpi_id not in self.kpis.index:
                continue
            kd = self.kpis.loc[kpi_id]
            krows = grouped.get(kpi_id, rows.iloc[0:0])
            krows = krows[krows["unit_id"].isin(info["leaves"]) | ~krows["unit_id"].isin(self.h.leaves)]
            agg = K.aggregate(krows, kd["aggregation"], float(kd["multiplier"]))
            tgt = self.target_for(kpi_id, scope.anchor_id, period.end)
            per_leaf = K.expected_periods(kd["frequency"], period.start, period.end, self.as_of or period.end)
            expected = per_leaf * len(info["leaves"])
            observed = int(krows["unit_id"].isin(info["leaves"]).sum())
            if expected == 0:
                rag_ = K.NOT_DUE if agg["value"] is None else (
                    K.rag(agg["value"], kd["direction"], tgt["green_threshold"], tgt["amber_threshold"], kd["decimals"])
                    if tgt else K.NO_DATA)
            elif tgt is None:
                rag_ = K.NO_DATA
            else:
                rag_ = K.rag(agg["value"], kd["direction"], tgt["green_threshold"], tgt["amber_threshold"], kd["decimals"])
            p = prev_by.get(kpi_id)
            results.append(H.KpiResult(
                kpi_id=kpi_id, code=kd["code"], name=kd["name"], unit=kd["unit"], decimals=int(kd["decimals"]),
                direction=kd["direction"], frequency=kd["frequency"], weight=info["weight"],
                actual=agg["value"], numerator=agg["numerator"], denominator=agg["denominator"],
                target=tgt["target"] if tgt else None, green=tgt["green_threshold"] if tgt else None,
                amber=tgt["amber_threshold"] if tgt else None, rag=rag_,
                meets_target=K.meets_target(agg["value"], tgt["target"] if tgt else None, kd["direction"], kd["decimals"]),
                expected=expected, observed=observed,
                previous=p.actual if p else None, previous_rag=p.rag if p else None))
        results.sort(key=lambda r: (-r.weight, r.code))
        out = H.score(results, self.rules)
        if self.rollup == "sites" and self._site_count(scope) > 1:
            self._roll_up(out, scope, period, with_previous)
        self._cache[key] = out
        return out

    def _site_count(self, scope: Scope) -> int:
        site = self.site_level()
        return sum(1 for u in scope.unit_ids if self.h.type[u] == site) if site else 0

    def _roll_up(self, out: H.HealthResult, scope: Scope, period: K.Period, with_previous: bool) -> None:
        """Health of a multi-site selection = simple average of its site scores, so a
        failing site is never hidden by good sites when volumes are pooled."""
        sites = self.site_results(scope, period, with_previous=with_previous)
        comps = [{"label": m["label"], "score": r.score, "status": r.status, "coverage": r.coverage}
                 for m, r in sites]
        usable = [c for c in comps if c["score"] is not None and c["status"] not in (H.INSUFFICIENT, K.NO_DATA)]
        cov = [c["coverage"] for c in comps if c["coverage"] is not None]
        out.components = comps
        out.rollup = "sites"
        out.coverage = sum(cov) / len(cov) if cov else None
        if not usable:
            out.score, out.status = None, K.NO_DATA
            return
        out.score = round(sum(c["score"] for c in usable) / len(usable), 1)
        out.status = H.band(out.score, out.coverage, self.rules)

    # ------------------------------------------------------------------ comparisons
    def _values(self, level: str, base: dict) -> list[str]:
        """Names at a level inside the selection (just the chosen one if that level is filtered)."""
        return [base[level]] if base.get(level) else self.h.options(level, base)

    def child_level(self, scope: Scope) -> str | None:
        chosen = {lv for lv, _ in scope.filters}
        for lv in self.h.levels:
            if lv not in chosen and len(self.h.options(lv, dict(scope.filters))) > 1:
                return lv
        return None

    def compare(self, scope: Scope, period: K.Period, level: str) -> pd.DataFrame:
        rows = []
        base = dict(scope.filters)
        for name in self._values(level, base):
            sub = self.h.scope({**base, level: name})
            if not sub.leaf_ids:
                continue
            r = self.evaluate(sub, period)
            prev = self.evaluate(sub, period.previous_month(), with_previous=False)
            rows.append({"name": name, "score": r.score, "status": r.status, "coverage": r.coverage,
                         "previous": prev.score, "kpis_met": r.met, "kpis_scored": len(r.scored),
                         "red_kpis": r.red})
        return pd.DataFrame(rows)

    def matrix(self, scope: Scope, period: K.Period, rows_level: str, cols_level: str) -> pd.DataFrame:
        base = dict(scope.filters)
        out = []
        for rname in self._values(rows_level, base):
            for cname in self._values(cols_level, {**base, rows_level: rname}):
                sub = self.h.scope({**base, rows_level: rname, cols_level: cname})
                if not sub.leaf_ids:
                    continue
                r = self.evaluate(sub, period)
                out.append({rows_level: rname, cols_level: cname, "score": r.score, "status": r.status,
                            "coverage": r.coverage, "red_kpis": r.red})
        return pd.DataFrame(out)

    def health_trend(self, scope: Scope, periods: list[K.Period]) -> pd.DataFrame:
        rows = []
        for p in periods:
            r = self.evaluate(scope, p, with_previous=False)
            rows.append({"period": p.label, "start": p.start, "score": r.score, "status": r.status,
                         "coverage": r.coverage, "kpis_met": r.met, "kpis_scored": len(r.scored)})
        return pd.DataFrame(rows)

    def kpi_series(self, scope: Scope, kpi_id: str, granularity: str, start: date, end: date) -> pd.DataFrame:
        """Actual vs target for one KPI by day / week / month (official calculation)."""
        kd = self.kpis.loc[kpi_id]
        rows = self._rows(scope, start, end, kpi_id).copy()
        if rows.empty:
            return pd.DataFrame(columns=["bucket", "actual", "target", "rag"])
        ts = pd.to_datetime(rows["d"])
        if granularity == "week":
            rows["bucket"] = (ts - pd.to_timedelta(ts.dt.weekday, unit="D")).dt.date
        elif granularity == "month":
            rows["bucket"] = ts.dt.to_period("M").dt.start_time.dt.date
        else:
            rows["bucket"] = rows["d"]
        out = []
        for b, g in rows.groupby("bucket"):
            agg = K.aggregate(g, kd["aggregation"], float(kd["multiplier"]))
            tgt = self.target_for(kpi_id, scope.anchor_id, b)
            out.append({"bucket": b, "actual": agg["value"], "target": tgt["target"] if tgt else None,
                        "rag": K.rag(agg["value"], kd["direction"], tgt["green_threshold"], tgt["amber_threshold"],
                                     kd["decimals"]) if tgt else K.NO_DATA, "observations": agg["n"]})
        return pd.DataFrame(out)

    # ------------------------------------------------------------------ risks & data gaps
    def site_level(self) -> str | None:
        lv = self.settings.get("alert_level")
        if lv in self.h.levels:
            return lv
        return "location" if "location" in self.h.levels else (self.h.levels[-2] if len(self.h.levels) > 1 else None)

    def site_results(self, scope: Scope, period: K.Period,
                     with_previous: bool = True) -> list[tuple[dict, H.HealthResult]]:
        """Evaluate every process x site inside the scope (the level where alerts are raised)."""
        site = self.site_level()
        parent_level = None
        if site and self.h.levels.index(site) > 0:
            parent_level = self.h.levels[self.h.levels.index(site) - 1]
        base = dict(scope.filters)
        out = []
        parents = self._values(parent_level, base) if parent_level else [None]
        for pname in parents:
            f = {**base, parent_level: pname} if parent_level else dict(base)
            for sname in self._values(site, f):
                sub = self.h.scope({**f, site: sname})
                if sub.leaf_ids:
                    out.append(({parent_level: pname, site: sname, "label": sub.label},
                                self.evaluate(sub, period, with_previous=with_previous)))
        return out

    def risks(self, scope: Scope, period: K.Period, limit: int | None = None) -> list[Risk]:
        site, out = self.site_level(), []
        parent_level = self.h.levels[self.h.levels.index(site) - 1] if site and self.h.levels.index(site) > 0 else None
        for meta, res in self.site_results(scope, period):
            for k in res.kpis:
                proc, loc = meta.get(parent_level), meta.get(site)
                if k.rag == "red" and k.target:
                    gap = abs(k.actual - k.target) / abs(k.target)
                    worsening = k.previous is not None and (
                        (k.actual < k.previous) if k.direction == "higher_better" else (k.actual > k.previous))
                    sev = k.weight * gap * (1.25 if worsening else 1.0)
                    detail = (f"{K.format_value(k.actual, k.unit, k.decimals, self.currency)} vs target "
                              f"{K.format_value(k.target, k.unit, k.decimals, self.currency)}")
                    if k.previous is not None:
                        detail += f" (previous month {K.format_value(k.previous, k.unit, k.decimals, self.currency)})"
                    out.append(Risk(meta["label"], proc, loc, k.code, k.name, k.actual, k.target, k.previous,
                                    k.rag, round(sev, 3), "performance", detail))
                elif k.expected > 0 and (k.coverage or 0) < 0.9:
                    missing = k.expected - k.observed
                    out.append(Risk(meta["label"], proc, loc, k.code, k.name, k.actual, k.target, k.previous,
                                    k.rag, round(k.weight * (1 - (k.coverage or 0)) * 0.1, 3), "data_gap",
                                    f"{missing} of {k.expected} expected {k.frequency} observations missing "
                                    f"({(k.coverage or 0):.0%} received)"))
        out.sort(key=lambda r: (r.kind != "performance", -r.severity))
        return out[:limit] if limit else out

    def critical_alerts(self, scope: Scope, period: K.Period) -> int:
        """Red KPI results at process x site level inside the scope."""
        return sum(r.red for _, r in self.site_results(scope, period))
