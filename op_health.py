"""Operational Health Score - transparent and configurable.

    Health score = Σ (KPI weight × RAG points) / Σ (weights of KPIs that HAVE data)

    * RAG points come from organisation settings (default Green 100, Amber 60, Red 20).
    * KPIs with no data are NOT counted as poor performance; they are excluded and
      reduce Data Coverage instead.
    * Data coverage = Σ (weight × share of due observations received) / Σ weights.
    * If coverage is below the minimum (default 60 %) the status is "Insufficient data".
    * Status bands from settings (default: >= 90 Green, >= 75 Amber, otherwise Red).

Roll-up above site level (default "sites"): the health of a selection that spans
several process sites (e.g. a whole client or the organisation) is the simple
average of the site health scores.  Sites with insufficient data are left out of
the average and reported.  Set organizations.settings.health.rollup = "kpis" to
score the pooled KPI values instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import op_config as config
from op_kpi import NO_DATA, NOT_DUE

INSUFFICIENT = "insufficient"


@dataclass
class KpiResult:
    kpi_id: str
    code: str
    name: str
    unit: str
    decimals: int
    direction: str
    frequency: str
    weight: float
    actual: float | None
    numerator: float | None
    denominator: float | None
    target: float | None
    green: float | None
    amber: float | None
    rag: str
    meets_target: bool | None
    expected: int
    observed: int
    points: float | None = None
    previous: float | None = None
    previous_rag: str | None = None

    @property
    def coverage(self) -> float | None:
        return None if self.expected == 0 else min(1.0, self.observed / self.expected)


@dataclass
class HealthResult:
    score: float | None
    status: str                    # green / amber / red / insufficient / no_data
    coverage: float | None
    kpis: list[KpiResult] = field(default_factory=list)
    rules: dict = field(default_factory=dict)
    rollup: str = "kpis"            # "kpis" = scored from KPI results; "sites" = average of site scores
    components: list = field(default_factory=list)   # site scores used when rollup == "sites"

    @property
    def scored(self) -> list[KpiResult]:
        return [k for k in self.kpis if k.rag not in (NO_DATA, NOT_DUE)]

    @property
    def met(self) -> int:
        return sum(1 for k in self.scored if k.meets_target)

    @property
    def red(self) -> int:
        return sum(1 for k in self.scored if k.rag == "red")


def rules_from_settings(settings: dict | None) -> dict:
    base = {k: (dict(v) if isinstance(v, dict) else v) for k, v in config.DEFAULT_HEALTH_RULES.items()}
    custom = (settings or {}).get("health") or {}
    for key in ("points", "bands"):
        base[key].update({k: float(v) for k, v in (custom.get(key) or {}).items()})
    if "min_coverage" in custom:
        base["min_coverage"] = float(custom["min_coverage"])
    return base


def score(kpis: list[KpiResult], rules: dict) -> HealthResult:
    pts = rules["points"]
    due = [k for k in kpis if k.rag != NOT_DUE and k.expected > 0]
    total_w = sum(k.weight for k in due)
    if not due or total_w == 0:
        return HealthResult(None, NO_DATA, None, kpis, rules)
    coverage = sum(k.weight * (k.coverage or 0.0) for k in due) / total_w
    scored = [k for k in due if k.rag not in (NO_DATA, NOT_DUE)]
    for k in kpis:
        k.points = pts.get(k.rag) if k.rag in pts else None
    scored_w = sum(k.weight for k in scored)
    if not scored or scored_w == 0:
        return HealthResult(None, NO_DATA, coverage, kpis, rules)
    value = round(sum(k.weight * k.points for k in scored) / scored_w, 1)   # status uses the shown number
    return HealthResult(value, band(value, coverage, rules), coverage, kpis, rules)


def band(value: float, coverage: float | None, rules: dict) -> str:
    if coverage is not None and coverage < rules["min_coverage"]:
        return INSUFFICIENT
    if value >= rules["bands"]["green"]:
        return "green"
    if value >= rules["bands"]["amber"]:
        return "amber"
    return "red"
