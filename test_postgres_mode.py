"""The app's data layer on real PostgreSQL: migrations + demo loader + KPI engine
must give exactly the same results as the built-in SQLite demo database."""
import tempfile
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")

from opspulse.data import db, repository, synthetic  # noqa: E402
from opspulse.engine import kpi as K  # noqa: E402
from opspulse.engine.analytics import Analyzer  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def pg_url():
    srv = pgserver.get_server(tempfile.mkdtemp(), cleanup_mode="stop")
    uri = srv.get_uri()
    with psycopg.connect(uri, autocommit=True) as c:
        c.execute((Path(__file__).parent / "supabase_stub.sql").read_text())
        for m in sorted((ROOT / "supabase" / "migrations").glob("*.sql")):
            c.execute(m.read_text())
    url = "postgresql+psycopg://" + uri.split("://", 1)[1]
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import load_demo_data
    assert load_demo_data.main(url) == 0
    assert load_demo_data.main(url) == 0          # second run is a no-op
    return url


def test_same_results_as_sqlite(pg_url, tmp_path):
    pg = Analyzer(repository.load_bundle(db.make_engine(pg_url), synthetic.ORG_ID))
    lite_engine = db.make_engine(f"sqlite:///{tmp_path / 'x.db'}")
    db.ensure_demo_database(lite_engine)
    lite = Analyzer(repository.load_bundle(lite_engine, synthetic.ORG_ID))
    sep = K.Period.month(2026, 9)
    for filters in ({}, {"process": "Refunds", "location": "Gurgaon"}, {"location": "Visakhapatnam"}):
        a, b = pg.evaluate(pg.h.scope(filters), sep), lite.evaluate(lite.h.scope(filters), sep)
        assert a.score == b.score and a.status == b.status
        assert [(k.code, round(k.actual, 6) if k.actual is not None else None) for k in a.kpis] == \
               [(k.code, round(k.actual, 6) if k.actual is not None else None) for k in b.kpis]


def test_writes_work_on_postgres(pg_url):
    eng = db.make_engine(pg_url)
    user = repository.user_by_email(eng, "demo.executive@example.com")
    new_id = repository.save_ai_insight(eng, synthetic.ORG_ID, unit_id=None, period_start="2026-09-01",
                                        period_end="2026-09-30", question="test", facts={"a": 1},
                                        explanations="", recommendations="", provider="fake", model="fake",
                                        user_id=str(user["id"]))
    repository.audit(eng, synthetic.ORG_ID, str(user["id"]), "export", "scorecard", None, {"x": 1})
    assert new_id


def test_app_runs_against_postgres(pg_url, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=240).run()
    assert not at.exception, [e.value for e in at.exception]
    md = " ".join(m.value for m in at.markdown)
    assert "Executive Command Center" in md
    assert any("Connected to PostgreSQL" in c.value for c in at.caption)
