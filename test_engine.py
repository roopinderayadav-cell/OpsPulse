"""KPI engine, synthetic data and AI-guard tests.   Run:  pytest -q"""
import hashlib
from datetime import date

import pandas as pd
import pytest

from opspulse.ai import commentary
from opspulse.data import db, repository, synthetic
from opspulse.engine import facts as F
from opspulse.engine import kpi as K
from opspulse.engine.analytics import Analyzer


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "demo.db"
    eng = db.make_engine(f"sqlite:///{path}")
    assert db.ensure_demo_database(eng) is True
    assert db.ensure_demo_database(eng) is False          # second call does not rebuild
    return eng


@pytest.fixture(scope="module")
def az(engine):
    return Analyzer(repository.load_bundle(engine, synthetic.ORG_ID))


SEP = K.Period.month(2026, 9)
AUG = K.Period.month(2026, 8)


# ------------------------------------------------------------------ synthetic data
def test_generator_is_deterministic():
    def digest():
        d = synthetic.generate()["kpi_observations"]
        return hashlib.sha256(pd.util.hash_pandas_object(d, index=False).values.tobytes()).hexdigest()
    assert digest() == digest()


def test_dataset_is_labelled_synthetic_and_covers_six_months():
    d = synthetic.generate()
    assert "Synthetic" in d["organizations"].iloc[0]["name"]
    assert d["organizations"].iloc[0]["is_demo"] == 1
    assert set(d["kpi_observations"]["source"]) == {"synthetic"}
    assert all("(Synthetic)" in n for n in d["users"]["full_name"])
    days = pd.to_datetime(d["kpi_observations"]["period_start"])
    assert days.min() == pd.Timestamp("2026-04-01") and days.max() == pd.Timestamp("2026-09-30")
    units = d["organizational_units"]
    assert set(units[units.unit_type == "location"]["name"]) == {"Bangalore", "Gurgaon", "Visakhapatnam"}
    assert set(units[units.unit_type == "process"]["name"]) == {
        "Corporate Travel Support", "Ticketing and Exchanges", "Refunds", "Back Office", "Customer Support"}


# ------------------------------------------------------------------ calculation rules
def test_ratio_of_sums_is_not_average_of_ratios():
    rows = pd.DataFrame({"numerator": [90, 10], "denominator": [100, 100], "value": [90.0, 10.0],
                         "unit_id": ["a", "b"], "period_start": pd.to_datetime(["2026-01-01"] * 2)})
    assert K.aggregate(rows, "ratio_of_sums", 100)["value"] == pytest.approx(50.0)
    rows.loc[1, "denominator"] = 20
    assert K.aggregate(rows, "ratio_of_sums", 100)["value"] == pytest.approx(100 / 120 * 100)
    assert K.aggregate(rows, "average")["value"] == pytest.approx(50.0)
    assert K.aggregate(rows, "weighted_average")["value"] == pytest.approx((90 * 100 + 10 * 20) / 120)
    assert K.aggregate(rows.iloc[0:0], "sum")["value"] is None


def test_last_takes_latest_per_unit_then_sums():
    rows = pd.DataFrame({"value": [5.0, 7.0, 3.0], "unit_id": ["a", "a", "b"],
                         "period_start": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-01"]),
                         "numerator": None, "denominator": None})
    assert K.aggregate(rows, "last")["value"] == 10.0


def test_unknown_aggregation_is_rejected():
    rows = pd.DataFrame({"value": [1.0], "numerator": [1], "denominator": [1], "unit_id": ["a"],
                         "period_start": pd.to_datetime(["2026-01-01"])})
    with pytest.raises(ValueError):
        K.aggregate(rows, "__import__('os').system('x')")


@pytest.mark.parametrize("value,direction,expected", [
    (95.0, "higher_better", "green"), (94.96, "higher_better", "green"),   # 94.96 shows as 95.0 -> green
    (94.94, "higher_better", "amber"), (90.0, "higher_better", "amber"), (89.9, "higher_better", "red"),
    (12.0, "lower_better", "green"), (13.5, "lower_better", "amber"), (13.6, "lower_better", "red"),
    (None, "higher_better", "no_data")])
def test_rag(value, direction, expected):
    green, amber = (95, 90) if direction == "higher_better" else (12, 13.5)
    assert K.rag(value, direction, green, amber, 1) == expected


def test_expected_periods_only_counts_closed_periods():
    assert K.expected_periods("daily", date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 30)) == 30
    assert K.expected_periods("daily", date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 10)) == 10
    assert K.expected_periods("monthly", date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 29)) == 0
    assert K.expected_periods("monthly", date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 30)) == 1
    assert K.expected_periods("weekly", date(2026, 9, 1), date(2026, 9, 30), date(2026, 10, 31)) == 4


# ------------------------------------------------------------------ health score on the demo data
def test_site_score_matches_hand_calculation(az):
    res = az.evaluate(az.h.scope({"process": "Refunds", "location": "Gurgaon"}), SEP)
    assert res.rollup == "kpis"
    pts = {"green": 100, "amber": 60, "red": 20}
    manual = sum(k.weight * pts[k.rag] for k in res.scored) / sum(k.weight for k in res.scored)
    assert res.score == round(manual, 1)
    assert res.status == "red"
    sla = next(k for k in res.kpis if k.code == "SLA")
    assert sla.actual == pytest.approx(sla.numerator / sla.denominator * 100)
    assert sla.rag == "red" and sla.previous is not None


def test_storylines_are_visible(az):
    gur = az.evaluate(az.h.scope({"process": "Refunds", "location": "Gurgaon"}), SEP)
    gur_apr = az.evaluate(az.h.scope({"process": "Refunds", "location": "Gurgaon"}), K.Period.month(2026, 4))
    assert gur.score < gur_apr.score - 30
    blr = az.evaluate(az.h.scope({"process": "Back Office", "location": "Bangalore"}), SEP)
    assert next(k for k in blr.kpis if k.code == "BACKLOG").rag == "red"
    cs = az.h.scope({"process": "Customer Support"})
    csat = [next(k for k in az.evaluate(cs, K.Period.month(2026, m)).kpis if k.code == "CSAT").actual for m in (4, 9)]
    assert csat[1] > csat[0] + 5


def test_missing_data_is_not_poor_performance(az):
    vz = az.evaluate(az.h.scope({"process": "Back Office", "location": "Visakhapatnam"}), SEP)
    q = next(k for k in vz.kpis if k.code == "QUALITY")
    assert q.rag == "no_data" and q.observed == 0 and q.expected == 60
    assert q.points is None                       # excluded, not scored as red
    assert vz.coverage < 1.0
    assert vz.score >= 90                         # remaining KPIs are healthy
    risks = az.risks(az.h.scope({}), SEP)
    assert any(r.kind == "data_gap" and r.kpi_code == "QUALITY" for r in risks)


def test_multi_site_rollup_is_average_of_sites(az):
    scope = az.h.scope({"process": "Refunds"})
    res = az.evaluate(scope, SEP)
    assert res.rollup == "sites" and len(res.components) == 3
    assert res.score == round(sum(c["score"] for c in res.components) / 3, 1)


def test_insufficient_data_status():
    from opspulse.engine import health as H
    ks = [H.KpiResult("k", "A", "A", "percent", 1, "higher_better", "daily", 10, 99, None, None, 95, 95, 90,
                      "green", True, expected=30, observed=10)]
    res = H.score(ks, H.rules_from_settings({}))
    assert res.status == H.INSUFFICIENT and res.score == 100


def test_results_are_reproducible(engine):
    a1 = Analyzer(repository.load_bundle(engine, synthetic.ORG_ID))
    a2 = Analyzer(repository.load_bundle(engine, synthetic.ORG_ID))
    s1, s2 = a1.evaluate(a1.h.scope({}), SEP), a2.evaluate(a2.h.scope({}), SEP)
    assert s1.score == s2.score
    assert [(k.code, k.actual) for k in s1.kpis] == [(k.code, k.actual) for k in s2.kpis]


def test_organisations_are_isolated(engine):
    from sqlalchemy import text
    with engine.begin() as c:
        c.execute(text("insert into organizations (id, name, slug, settings, is_demo) "
                       "values ('other-org', 'Other Co', 'other-co', '{}', 0)"))
    other = repository.load_bundle(engine, "other-org")
    assert other.observations.empty and other.units.empty and other.kpis.empty
    with pytest.raises(LookupError):
        repository.load_bundle(engine, "does-not-exist")


def test_facts_contain_only_engine_numbers(az):
    f = F.build(az, az.h.scope({"process": "Refunds"}), SEP)
    assert f["data_label"] == "SYNTHETIC DEMO DATA"
    assert f["health_score"] == az.evaluate(az.h.scope({"process": "Refunds"}), SEP).score
    assert any("Gurgaon" in r["where"] for r in f["top_risks"])
    assert F.sentences(f)[0].startswith("Operational health for Refunds in Sep 2026")


# ------------------------------------------------------------------ AI guard rails (no network)
class FakeProvider:
    name, model = "fake", "fake-1"

    def __init__(self, reply):
        self.reply = reply
        self.prompt = None

    def generate_json(self, prompt, max_tokens=1500):
        self.prompt = prompt
        return self.reply


def test_ai_summary_flags_invented_numbers_and_labels_hypotheses(az):
    f = F.build(az, az.h.scope({"process": "Refunds", "location": "Gurgaon"}), SEP)
    reply = {"headline": f"Health is {f['health_score']}",
             "confirmed_facts": [f"Health is {f['health_score']} and churn is 12.34%"],
             "possible_explanations": ["Attrition rose in July"],
             "recommendations": [{"action": "Review staffing", "kpi": "SLA", "where": "Gurgaon"}]}
    fake = FakeProvider(reply)
    out = commentary.executive_summary(f, provider=fake)
    assert out["unverified_numbers"] == [12.34]
    assert out["possible_explanations"][0]["text"].startswith("Possibly")
    assert "VERIFIED FACTS" in fake.prompt and "never" in fake.prompt.lower()
    assert out["provider"] == "fake"
