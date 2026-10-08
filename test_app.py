"""Headless UI smoke tests with Streamlit's AppTest.   Run:  pytest -q"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = str(Path(__file__).resolve().parents[1])
APP = str(Path(ROOT) / "app.py")


@pytest.fixture(autouse=True)
def no_ai(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ACCESS_CODE", raising=False)


def run(at):
    at.run(timeout=180)
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_command_center_renders():
    at = run(AppTest.from_file(APP))
    md = " ".join(m.value for m in at.markdown)
    assert "Executive Command Center" in md and "SYNTHETIC DEMO DATA" in md
    assert "Verified facts" in md and "AI executive summary" in md
    assert "AI commentary is off" in md


def test_drill_down_with_filters():
    at = run(AppTest.from_file(APP))
    at.selectbox(key="f_process").select("Refunds").run(timeout=180)
    at.selectbox(key="f_location").select("Gurgaon").run(timeout=180)
    assert not at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "Refunds › Gurgaon" in md
    assert "Critical" in md


def test_previous_month_and_reset():
    at = run(AppTest.from_file(APP))
    at.selectbox(key="f_period").select("Apr 2026").run(timeout=180)
    assert not at.exception
    at.selectbox(key="f_process").select("Back Office").run(timeout=180)
    at.button[0].click().run(timeout=180)     # Reset
    assert at.selectbox(key="f_process").value == "All"


def test_access_code_gate(monkeypatch):
    monkeypatch.setenv("APP_ACCESS_CODE", "demo-code-for-test")
    at = run(AppTest.from_file(APP))
    assert at.text_input[0].label == "Access code"
    at.text_input[0].input("wrong")
    at.button[0].click().run(timeout=60)
    assert any("not correct" in e.value for e in at.error)
    at.text_input[0].input("demo-code-for-test")
    at.button[0].click().run(timeout=180)
    assert not at.exception
    assert "Executive Command Center" in " ".join(m.value for m in at.markdown)


def _page_script(key, root):
    import sys
    sys.path.insert(0, root)
    from opspulse.ui import session, theme
    from opspulse.views import modules
    theme.apply()
    ctx = session.load_context()
    if key == "organization":
        modules.org_preview(ctx)
    elif key == "kpi-studio":
        modules.kpi_preview(ctx)
    else:
        modules.planned(key)()


@pytest.mark.parametrize("page", ["organization", "kpi-studio"] + list(__import__("opspulse.views.modules",
                                                                                 fromlist=["MODULES"]).MODULES))
def test_other_pages_render(page):
    at = AppTest.from_function(_page_script, args=(page, ROOT), default_timeout=180)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    md = " ".join(m.value for m in at.markdown)
    if page not in ("organization", "kpi-studio"):
        assert "PLANNED" in md          # unbuilt modules are always labelled as planned
