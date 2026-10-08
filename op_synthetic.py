"""Synthetic demonstration dataset - corporate travel operations.

EVERYTHING produced here is FICTIONAL.  Client names, people and numbers are
invented for demonstrations.  The generator is deterministic (fixed seed and
fixed IDs) so every run produces exactly the same data and the same KPI results.

Built-in storylines (so dashboards have something real to show):
  1. Refunds - Gurgaon: attrition spike in July, then productivity, backlog and
     SLA deteriorate through August and September.
  2. Back Office - Bangalore: backlog days rise steadily from June.
  3. Back Office - Visakhapatnam: Quality audits are MISSING from 1 August
     (demonstrates "missing data" vs "poor performance").
  4. Customer Support (all sites): CSAT improves month after month.
  5. Ticketing and Exchanges - Visakhapatnam: AHT improves after process changes.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

import numpy as np
import pandas as pd

NAMESPACE = uuid.UUID("6f1d7c1e-0b7a-4c5e-9d55-1f0b5a3c9e01")   # fixed -> stable IDs
START, END = date(2026, 4, 1), date(2026, 9, 30)                  # six full months
SEED = 20260401
LOCATIONS = ["Bangalore", "Gurgaon", "Visakhapatnam"]
ORG_SLUG = "demo-travel-ops"


def sid(*parts: str) -> str:
    """Stable UUID from a readable key, e.g. sid('unit', 'Refunds', 'Gurgaon')."""
    return str(uuid.uuid5(NAMESPACE, "/".join(parts)))


ORG_ID = sid("org", ORG_SLUG)

# code, name, description, unit, calc_type, num_label, den_label, multiplier, direction,
# frequency, aggregation, decimals, target, green, amber
KPIS = [
    ("SLA", "Service Level (SLA)", "Share of requests completed within the agreed service level.",
     "percent", "ratio", "Requests within SLA", "Total requests", 100, "higher_better", "daily", "ratio_of_sums", 1, 95, 95, 90),
    ("QUALITY", "Quality Score", "Audit points achieved as a share of points possible.",
     "percent", "ratio", "Audit points achieved", "Audit points possible", 100, "higher_better", "daily", "ratio_of_sums", 1, 97, 97, 94),
    ("PRODUCTIVITY", "Productivity", "Transactions completed per productive hour.",
     "ratio", "ratio", "Transactions completed", "Productive hours", 1, "higher_better", "daily", "ratio_of_sums", 2, 6.0, 6.0, 5.5),
    ("AHT", "Average Handle Time", "Average minutes spent handling one contact.",
     "minutes", "ratio", "Total handle minutes", "Contacts handled", 1, "lower_better", "daily", "ratio_of_sums", 1, 12.0, 12.0, 13.5),
    ("CSAT", "Customer Satisfaction (CSAT)", "Satisfied survey responses as a share of all responses.",
     "percent", "ratio", "Satisfied responses", "Survey responses", 100, "higher_better", "daily", "ratio_of_sums", 1, 85, 85, 80),
    ("FCR", "First Contact Resolution", "Contacts resolved without a repeat contact.",
     "percent", "ratio", "Resolved on first contact", "Contacts", 100, "higher_better", "daily", "ratio_of_sums", 1, 75, 75, 70),
    ("BACKLOG", "Backlog (days of work)", "Open items at end of day divided by daily incoming volume.",
     "ratio", "ratio", "Open items (end of day)", "Incoming volume", 1, "lower_better", "daily", "ratio_of_sums", 2, 1.0, 1.0, 1.5),
    ("ATTRITION", "Monthly Attrition", "Leavers as a share of average headcount in the month.",
     "percent", "ratio", "Leavers", "Average headcount", 100, "lower_better", "monthly", "ratio_of_sums", 1, 3.0, 3.0, 4.5),
    ("COST", "Cost per Transaction", "Total operating cost divided by transactions completed (INR).",
     "currency", "ratio", "Operating cost (INR)", "Transactions completed", 1, "lower_better", "monthly", "ratio_of_sums", 1, 85, 85, 92),
]
KPI_WEIGHTS = {"SLA": 25, "QUALITY": 20, "CSAT": 15, "FCR": 10, "AHT": 10, "PRODUCTIVITY": 10,
               "BACKLOG": 10, "ATTRITION": 5, "COST": 5}

# client -> processes, and the KPI set each process is measured on
CLIENTS = {
    "Client Aurora (Synthetic)": ["Corporate Travel Support", "Ticketing and Exchanges", "Refunds"],
    "Client Meridian (Synthetic)": ["Back Office", "Customer Support"],
}
PROCESS_KPIS = {
    "Corporate Travel Support": ["SLA", "QUALITY", "AHT", "CSAT", "FCR", "PRODUCTIVITY", "ATTRITION", "COST"],
    "Ticketing and Exchanges": ["SLA", "QUALITY", "AHT", "PRODUCTIVITY", "BACKLOG", "ATTRITION", "COST"],
    "Refunds": ["SLA", "QUALITY", "PRODUCTIVITY", "BACKLOG", "CSAT", "ATTRITION", "COST"],
    "Back Office": ["SLA", "QUALITY", "PRODUCTIVITY", "BACKLOG", "ATTRITION", "COST"],
    "Customer Support": ["SLA", "QUALITY", "AHT", "CSAT", "FCR", "ATTRITION", "COST"],
}
PROCESS_VOLUME = {"Corporate Travel Support": 260, "Ticketing and Exchanges": 210, "Refunds": 140,
                  "Back Office": 180, "Customer Support": 300}
# process-specific target override (Back Office runs to a tighter SLA)
TARGET_OVERRIDES = [("SLA", "Back Office", 97, 97, 93)]


def _ramp(d: date, start: date, end: date, a: float, b: float) -> float:
    """Linear change from a (on/before start) to b (on/after end)."""
    if d <= start:
        return a
    if d >= end:
        return b
    return a + (b - a) * (d - start).days / (end - start).days


def _drivers(process: str, loc: str, d: date) -> dict:
    """Underlying performance levels for a site on a day (before random noise)."""
    p = dict(sla=0.962, quality=0.978, prod=6.35, aht=11.3, csat=0.865, fcr=0.775,
             backlog=0.78, attrition=0.024, cost=80.0)
    site_bias = {"Bangalore": 0.0, "Gurgaon": -0.004, "Visakhapatnam": 0.002}[loc]
    p["sla"] += site_bias
    if process == "Refunds" and loc == "Gurgaon":                       # storyline 1
        p["attrition"] = {7: 0.095, 8: 0.07, 9: 0.05}.get(d.month, 0.026)
        p["prod"] = _ramp(d, date(2026, 7, 15), date(2026, 9, 15), 6.3, 5.35)
        p["backlog"] = _ramp(d, date(2026, 7, 20), date(2026, 9, 30), 0.82, 1.75)
        p["sla"] = _ramp(d, date(2026, 7, 25), date(2026, 9, 30), 0.958, 0.855)
        p["cost"] = _ramp(d, date(2026, 7, 1), date(2026, 9, 30), 81, 96)
        p["csat"] = _ramp(d, date(2026, 8, 1), date(2026, 9, 30), 0.86, 0.80)
    if process == "Back Office" and loc == "Bangalore":                 # storyline 2
        p["backlog"] = _ramp(d, date(2026, 6, 1), date(2026, 9, 30), 0.8, 1.68)
        p["sla"] = _ramp(d, date(2026, 8, 1), date(2026, 9, 30), 0.975, 0.945)
    if process == "Back Office":
        p["sla"] = max(p["sla"], 0.0) + (0.012 if loc != "Bangalore" else 0.0)
    if process == "Customer Support":                                   # storyline 4
        p["csat"] = _ramp(d, START, END, 0.785, 0.885)
        p["aht"] = 10.6
    if process == "Ticketing and Exchanges" and loc == "Visakhapatnam":  # storyline 5
        p["aht"] = _ramp(d, START, date(2026, 8, 31), 14.2, 11.2)
    if process == "Corporate Travel Support":
        p["aht"] = 11.6
    return p


def generate() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    settings = {
        "currency": "INR",
        "hierarchy_levels": ["business_unit", "client", "process", "location", "team"],
        "level_labels": {"business_unit": "Business Unit", "client": "Client", "process": "Process",
                         "location": "Location", "team": "Team"},
        "health": {"points": {"green": 100, "amber": 60, "red": 20},
                   "bands": {"green": 90, "amber": 75}, "min_coverage": 0.6},
        "synthetic_notice": "All data in this organisation is synthetic and for demonstration only.",
    }
    orgs = pd.DataFrame([dict(id=ORG_ID, name="Demo Travel Operations (Synthetic)", slug=ORG_SLUG,
                              industry="Corporate travel management", settings=json.dumps(settings), is_demo=1)])
    users = pd.DataFrame([
        dict(id=sid("user", "exec"), email="demo.executive@example.com", full_name="Demo Executive (Synthetic)"),
        dict(id=sid("user", "analyst"), email="demo.analyst@example.com", full_name="Demo Analyst (Synthetic)"),
    ])
    memberships = pd.DataFrame([
        dict(id=sid("mem", "exec"), organization_id=ORG_ID, user_id=sid("user", "exec"), role="owner", status="active"),
        dict(id=sid("mem", "analyst"), organization_id=ORG_ID, user_id=sid("user", "analyst"), role="analyst", status="active"),
    ])

    units, leaves = [], []          # leaves: (team_id, process, location)

    def add(key, parent, utype, name):
        uid = sid("unit", *key)
        units.append(dict(id=uid, organization_id=ORG_ID, parent_id=parent, unit_type=utype, name=name,
                          code=None, is_active=1))
        return uid

    bu = add(("bu",), None, "business_unit", "Corporate Travel Operations")
    process_ids = {}
    for client, procs in CLIENTS.items():
        cid = add(("client", client), bu, "client", client)
        for proc in procs:
            pid = add(("process", proc), cid, "process", proc)
            process_ids[proc] = pid
            for loc in LOCATIONS:
                lid = add(("loc", proc, loc), pid, "location", loc)
                for t in (1, 2):
                    tid = add(("team", proc, loc, str(t)), lid, "team", f"{proc} - {loc} - Team {t}")
                    leaves.append((tid, proc, loc))

    kpis, targets = [], []
    for (code, name, desc, unit, calc, num, den, mult, direction, freq, agg, dec, tgt, g, a) in KPIS:
        kid = sid("kpi", code)
        kpis.append(dict(id=kid, organization_id=ORG_ID, code=code, name=name, description=desc, unit=unit,
                         calc_type=calc, numerator_label=num, denominator_label=den, multiplier=mult,
                         direction=direction, frequency=freq, aggregation=agg, decimals=dec,
                         owner_user_id=sid("user", "analyst"), is_active=1))
        targets.append(dict(id=sid("target", code), organization_id=ORG_ID, kpi_id=kid, unit_id=None,
                            target=tgt, green_threshold=g, amber_threshold=a,
                            effective_from="2026-01-01", effective_to=None))
    for code, proc, tgt, g, a in TARGET_OVERRIDES:
        targets.append(dict(id=sid("target", code, proc), organization_id=ORG_ID, kpi_id=sid("kpi", code),
                            unit_id=process_ids[proc], target=tgt, green_threshold=g, amber_threshold=a,
                            effective_from="2026-01-01", effective_to=None))

    assignments = []
    for proc, codes in PROCESS_KPIS.items():
        for code in codes:
            assignments.append(dict(id=sid("assign", proc, code), organization_id=ORG_ID, kpi_id=sid("kpi", code),
                                    unit_id=process_ids[proc], weight=KPI_WEIGHTS[code],
                                    effective_from="2026-01-01", effective_to=None))

    obs = []
    days = [START + timedelta(n) for n in range((END - START).days + 1)]

    def put(kpi, unit_id, ptype, pstart, num, den, mult):
        num, den = float(round(num, 2)), float(round(den, 2))
        value = round(num / den * mult, 4) if den else None
        if value is None:
            return
        obs.append(dict(id=sid("obs", kpi, unit_id, ptype, pstart), organization_id=ORG_ID, kpi_id=sid("kpi", kpi),
                        unit_id=unit_id, period_type=ptype, period_start=pstart, value=value, numerator=num,
                        denominator=den, status="approved", source="synthetic"))

    for tid, proc, loc in leaves:
        codes = PROCESS_KPIS[proc]
        base = PROCESS_VOLUME[proc] * rng.uniform(0.85, 1.15)
        monthly_tx = {}
        for d in days:
            dr = _drivers(proc, loc, d)
            weekend = d.weekday() >= 5
            vol = int(rng.poisson(base * (0.55 if weekend else 1.0)))
            if vol <= 0:
                continue
            ds = d.isoformat()
            monthly_tx[d.month] = monthly_tx.get(d.month, 0) + vol
            if "SLA" in codes:
                p = float(np.clip(dr["sla"] + rng.normal(0, 0.012), 0.5, 1.0))
                put("SLA", tid, "day", ds, rng.binomial(vol, p), vol, 100)
            if "QUALITY" in codes and not (proc == "Back Office" and loc == "Visakhapatnam" and d >= date(2026, 8, 1)):
                possible = 10 * 100
                q = float(np.clip(dr["quality"] + rng.normal(0, 0.008), 0.8, 1.0))
                put("QUALITY", tid, "day", ds, possible * q, possible, 100)
            if "PRODUCTIVITY" in codes:
                rate = max(3.0, dr["prod"] + rng.normal(0, 0.25))
                put("PRODUCTIVITY", tid, "day", ds, vol, vol / rate, 1)
            if "AHT" in codes:
                aht = max(5.0, dr["aht"] + rng.normal(0, 0.6))
                put("AHT", tid, "day", ds, vol * aht, vol, 1)
            if "CSAT" in codes:
                resp = max(5, int(vol * 0.15))
                p = float(np.clip(dr["csat"] + rng.normal(0, 0.03), 0.3, 1.0))
                put("CSAT", tid, "day", ds, rng.binomial(resp, p), resp, 100)
            if "FCR" in codes:
                p = float(np.clip(dr["fcr"] + rng.normal(0, 0.02), 0.3, 1.0))
                put("FCR", tid, "day", ds, rng.binomial(vol, p), vol, 100)
            if "BACKLOG" in codes:
                bl = max(0.05, dr["backlog"] + rng.normal(0, 0.08))
                put("BACKLOG", tid, "day", ds, round(vol * bl), vol, 1)
        for m in range(START.month, END.month + 1):
            first = date(2026, m, 1)
            dr = _drivers(proc, loc, first + timedelta(14))
            hc = int(rng.integers(22, 34))
            leavers = int(round(hc * dr["attrition"] * rng.uniform(0.6, 1.4)))
            put("ATTRITION", tid, "month", first.isoformat(), leavers, hc, 100)
            tx = monthly_tx.get(m, 0)
            cpt = max(40.0, dr["cost"] + rng.normal(0, 2.0))
            put("COST", tid, "month", first.isoformat(), tx * cpt, tx, 1)

    return {
        "organizations": orgs, "users": users, "memberships": memberships,
        "organizational_units": pd.DataFrame(units), "kpi_definitions": pd.DataFrame(kpis),
        "kpi_assignments": pd.DataFrame(assignments), "kpi_targets": pd.DataFrame(targets),
        "kpi_observations": pd.DataFrame(obs),
    }


# Order matters: parents before children (foreign keys)
TABLE_ORDER = ["organizations", "users", "memberships", "organizational_units", "kpi_definitions",
               "kpi_assignments", "kpi_targets", "kpi_observations"]


def write_csvs(folder) -> list[str]:
    """Write the dataset as CSV files (for inspection or Data Hub upload tests)."""
    from pathlib import Path
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    data = generate()
    written = []
    readme = folder / "README.txt"
    readme.write_text("SYNTHETIC DEMONSTRATION DATA - fictional corporate travel operations.\n"
                      "Generated by opspulse/data/synthetic.py (deterministic). Not real company data.\n")
    for name in TABLE_ORDER:
        path = folder / f"{name}.csv"
        data[name].to_csv(path, index=False)
        written.append(str(path))
    return written


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "data/sample"
    for p in write_csvs(out):
        print("wrote", p)
