"""All database reads and writes go through this module.

Tenant rule: every function that touches business data takes ``org_id`` and
filters on it.  Pages never write SQL themselves.  (In Phase 2 Supabase
Row Level Security adds a second, database-side guarantee per signed-in user.)
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass
class OrgBundle:
    """Everything the KPI engine needs for one organisation."""
    org: dict
    units: pd.DataFrame
    kpis: pd.DataFrame
    assignments: pd.DataFrame
    targets: pd.DataFrame
    observations: pd.DataFrame


def _df(engine: Engine, sql: str, **params) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def organizations_for_user(engine: Engine, user_id: str) -> pd.DataFrame:
    return _df(engine, """
        select o.id, o.name, o.slug, o.is_demo, m.role
        from organizations o join memberships m on m.organization_id = o.id
        where m.user_id = :uid and m.status = 'active' order by o.name""", uid=user_id)


def user_by_email(engine: Engine, email: str) -> dict | None:
    df = _df(engine, "select id, email, full_name from users where lower(email) = lower(:e)", e=email)
    return None if df.empty else df.iloc[0].to_dict()


def load_bundle(engine: Engine, org_id: str) -> OrgBundle:
    org = _df(engine, "select id, name, slug, industry, settings, is_demo from organizations where id = :o", o=org_id)
    if org.empty:
        raise LookupError("Organisation not found or not accessible.")
    org_row = org.iloc[0].to_dict()
    settings = org_row.get("settings")
    if isinstance(settings, str):
        settings = json.loads(settings or "{}")
    org_row["settings"] = settings or {}
    org_row["id"] = str(org_row["id"])

    units = _df(engine, """select id, parent_id, unit_type, name, code from organizational_units
                           where organization_id = :o and is_active = :t""", o=org_id, t=True)
    kpis = _df(engine, """select id, code, name, description, unit, calc_type, numerator_label,
                                 denominator_label, multiplier, direction, frequency, aggregation, decimals
                          from kpi_definitions where organization_id = :o and is_active = :t""", o=org_id, t=True)
    assignments = _df(engine, """select kpi_id, unit_id, weight, effective_from, effective_to
                                 from kpi_assignments where organization_id = :o""", o=org_id)
    targets = _df(engine, """select kpi_id, unit_id, target, green_threshold, amber_threshold,
                                    effective_from, effective_to
                             from kpi_targets where organization_id = :o""", o=org_id)
    # Only APPROVED data is used for official KPI results.
    obs = _df(engine, """select kpi_id, unit_id, period_type, period_start, value, numerator, denominator
                         from kpi_observations where organization_id = :o and status = 'approved'""", o=org_id)

    for df, cols in ((units, ["id", "parent_id"]), (kpis, ["id"]), (assignments, ["kpi_id", "unit_id"]),
                     (targets, ["kpi_id", "unit_id"]), (obs, ["kpi_id", "unit_id"])):
        for c in cols:   # Postgres returns UUID objects, SQLite returns text -> normalise to text
            df[c] = df[c].map(lambda v: None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v))
    for df, cols in ((assignments, ["effective_from", "effective_to"]),
                     (targets, ["effective_from", "effective_to"]), (obs, ["period_start"])):
        for c in cols:
            df[c] = pd.to_datetime(df[c])
    for c in ("value", "numerator", "denominator"):
        obs[c] = pd.to_numeric(obs[c], errors="coerce")
    for c in ("multiplier",):
        kpis[c] = pd.to_numeric(kpis[c])
    for c in ("target", "green_threshold", "amber_threshold"):
        targets[c] = pd.to_numeric(targets[c])
    assignments["weight"] = pd.to_numeric(assignments["weight"])
    return OrgBundle(org_row, units, kpis, assignments, targets, obs)


def save_ai_insight(engine: Engine, org_id: str, *, unit_id: str | None, period_start, period_end,
                    question: str, facts: dict, explanations: str, recommendations: str,
                    provider: str, model: str, user_id: str | None) -> str:
    new_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""insert into ai_insights (id, organization_id, unit_id, period_start, period_end, question,
                             facts, explanations, recommendations, provider, model, created_by)
                             values (:id, :o, :u, :ps, :pe, :q, :f, :e, :r, :p, :m, :by)"""),
                     dict(id=new_id, o=org_id, u=unit_id, ps=str(period_start), pe=str(period_end), q=question,
                          f=json.dumps(facts, default=str), e=explanations, r=recommendations,
                          p=provider, m=model, by=user_id))
    return new_id


def audit(engine: Engine, org_id: str | None, user_id: str | None, action: str, entity_type: str,
          entity_id: str | None = None, after: dict | None = None) -> None:
    """Application-level audit entry (exports, AI calls, sign-ins).  Data changes in
    Supabase are additionally captured by database triggers (see 0002_rls.sql)."""
    with engine.begin() as conn:
        conn.execute(text("""insert into audit_logs (organization_id, actor_user_id, action, entity_type, entity_id, after_data)
                             values (:o, :u, :a, :t, :i, :d)"""),
                     dict(o=org_id, u=user_id, a=action, t=entity_type, i=entity_id,
                          d=json.dumps(after, default=str) if after else None))
