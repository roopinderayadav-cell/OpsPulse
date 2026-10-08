"""KPI calculation rules.  Pure functions: same inputs -> same result, always.

Only a fixed list of safe calculations exists.  Nothing a user types is ever
executed as code.

calc_type
  direct  - the value is entered as-is (e.g. headcount, an index score)
  ratio   - value = numerator / denominator x multiplier (e.g. SLA % = met / total x 100)

aggregation (how many observations become one number)
  ratio_of_sums    - sum(numerators) / sum(denominators) x multiplier   (correct for %/rates)
  sum              - total of values
  average          - simple mean of values
  weighted_average - mean of values weighted by denominator (volume)
  last             - latest period per unit, then summed across units (stock figures such as headcount)
  min / max        - lowest / highest value
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

RAG_GREEN, RAG_AMBER, RAG_RED, NO_DATA, NOT_DUE = "green", "amber", "red", "no_data", "not_due"


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str

    @staticmethod
    def month(year: int, month: int) -> "Period":
        last = calendar.monthrange(year, month)[1]
        return Period(date(year, month, 1), date(year, month, last), date(year, month, 1).strftime("%b %Y"))

    def previous_month(self) -> "Period":
        prev = self.start - timedelta(days=1)
        return Period.month(prev.year, prev.month)


def months_between(first: date, last: date) -> list[Period]:
    out, y, m = [], first.year, first.month
    while (y, m) <= (last.year, last.month):
        out.append(Period.month(y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def aggregate(rows: pd.DataFrame, aggregation: str, multiplier: float = 1.0) -> dict:
    """Combine observation rows into one result.

    Returns {"value": float|None, "numerator": float|None, "denominator": float|None, "n": int}."""
    n = int(len(rows))
    if n == 0:
        return {"value": None, "numerator": None, "denominator": None, "n": 0}
    if aggregation == "ratio_of_sums":
        num, den = float(rows["numerator"].sum()), float(rows["denominator"].sum())
        val = (num / den * multiplier) if den else None
        return {"value": val, "numerator": num, "denominator": den, "n": n}
    vals = rows["value"].astype(float)
    if aggregation == "sum":
        val = float(vals.sum())
    elif aggregation == "average":
        val = float(vals.mean())
    elif aggregation == "weighted_average":
        w = rows["denominator"].astype(float)
        val = float((vals * w).sum() / w.sum()) if w.sum() else None
    elif aggregation == "last":
        latest = rows.sort_values("period_start").groupby("unit_id").tail(1)
        val = float(latest["value"].astype(float).sum())
    elif aggregation == "min":
        val = float(vals.min())
    elif aggregation == "max":
        val = float(vals.max())
    else:
        raise ValueError(f"Unknown aggregation rule: {aggregation}")
    return {"value": val, "numerator": None, "denominator": None, "n": n}


def rag(value: float | None, direction: str, green: float, amber: float, decimals: int = 1) -> str:
    """Red / Amber / Green.  The value is rounded to the KPI's display decimals first,
    so the colour always matches the number people see."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return NO_DATA
    v = round(float(value), int(decimals))
    if direction == "higher_better":
        return RAG_GREEN if v >= green else RAG_AMBER if v >= amber else RAG_RED
    return RAG_GREEN if v <= green else RAG_AMBER if v <= amber else RAG_RED


def meets_target(value: float | None, target: float | None, direction: str, decimals: int = 1) -> bool | None:
    if value is None or target is None:
        return None
    v = round(float(value), int(decimals))
    return v >= target if direction == "higher_better" else v <= target


def expected_periods(frequency: str, start: date, end: date, as_of: date) -> int:
    """How many observations of this frequency are DUE in [start, end] by ``as_of``.

    A period only counts once it has fully ended, so a monthly KPI is not 'missing'
    before the month closes."""
    last = min(end, as_of)
    if last < start:
        return 0
    if frequency == "daily":
        return (last - start).days + 1
    if frequency == "weekly":   # weeks start on Monday and belong to the period they start in
        first_monday = start + timedelta(days=(7 - start.weekday()) % 7)
        count, d = 0, first_monday
        while d <= end:
            if d + timedelta(days=6) <= as_of:
                count += 1
            d += timedelta(days=7)
        return count
    if frequency == "monthly":
        count, p = 0, Period.month(start.year, start.month)
        while p.start <= end:
            if p.start >= start and p.end <= as_of:
                count += 1
            nxt = p.end + timedelta(days=1)
            p = Period.month(nxt.year, nxt.month)
        return count
    raise ValueError(f"Unknown frequency: {frequency}")


def format_value(value: float | None, unit: str, decimals: int = 1, currency: str = "INR") -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    d = int(decimals)
    if unit == "percent":
        return f"{value:,.{d}f}%"
    if unit == "currency":
        sym = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(currency, currency + " ")
        return f"{sym}{value:,.{d}f}"
    if unit in ("minutes", "seconds", "hours"):
        return f"{value:,.{d}f} {unit[:3] if unit != 'hours' else 'hrs'}"
    return f"{value:,.{d}f}"
