# OpsPulse AI — AI-Powered Operations Intelligence Platform

**From Data to Decisions.** Phase 1 · Module 1 — Application Foundation and Executive Command Center.

> All data shipped with this repository is **synthetic** (fictional corporate-travel operations).
> Keep this repository **private**.

## What works today vs. what is planned

| Module | Status |
|---|---|
| A. Executive Command Center | **Functional** – health score, KPI cards, trend, comparison with click-to-drill, scorecard, top risks, process × location map, verified facts, optional Gemini summary, KPI drill-down, Excel export |
| KPI calculation engine | **Functional** – fixed safe calculation types, RAG, targets with overrides, data coverage, reproducible results, automated tests |
| Database (Supabase/PostgreSQL) | **Functional** – 15-table schema, Row Level Security, audit triggers, tested on PostgreSQL 16 |
| B. Organization Setup | Read-only hierarchy preview · editing **planned** (Module 2) |
| C. KPI Studio | Read-only KPI catalogue · builder **planned** (Module 3) |
| D. Data Hub, E. Process Analytics, F. AI Analyst, G. PowerPoint Studio | **Planned** (Modules 4–7) – design previews only |
| H. Actions & Alerts, I. Leadership Mobile, J. Admin & Security, sign-in | **Planned** (Phase 2) |

The Command Center already adapts to phone screens; the dedicated mobile view is planned.

## Folder structure

```
app.py                         ← start file (Streamlit "Main file path")
requirements.txt               ← packages Streamlit Cloud installs
requirements-dev.txt           ← extra packages for running tests
START_APP.bat                  ← Windows: double-click to run locally
.streamlit/config.toml         ← colours, fonts, server settings
.streamlit/secrets.toml.example← which secrets exist (copy into Streamlit Cloud)
assets/                        ← logo and icon
opspulse/
  config.py                    ← settings; reads secrets, never stores them
  data/  db.py repository.py schema_sqlite.sql synthetic.py
  engine/ kpi.py health.py hierarchy.py analytics.py facts.py   ← official calculations (no AI)
  ai/    provider.py commentary.py                              ← Gemini, number check
  ui/    theme.py components.py charts.py session.py
  views/ command_center.py modules.py
supabase/migrations/0001_schema.sql, 0002_rls.sql
scripts/load_demo_data.py      ← loads the synthetic demo into Supabase
data/sample/*.csv              ← the synthetic dataset as CSV
tests/                         ← automated tests (engine, app, database security)
```

## Run on your computer (Windows)

1. Install Python 3.12 from python.org (tick “Add Python to PATH”).
2. Double-click `START_APP.bat`. The first run installs packages (a few minutes).
3. The browser opens at http://localhost:8501. The demo database is created automatically.

## Deploy to Streamlit Community Cloud

1. GitHub → **New repository** → name `opspulse-ai` → **Private** → Create.
2. **Add file → Upload files** → drag in everything from this folder *except* `.venv` and `data/*.db` → Commit.
3. share.streamlit.io → **Create app** → choose the repo, branch `main`, main file path **`app.py`**.
4. **Advanced settings** → Python **3.12** → Secrets: paste what you need from `.streamlit/secrets.toml.example`
   (all optional). Recommended for a private demo: `APP_ACCESS_CODE = "a-long-code"`.
5. Deploy. The first start takes a few minutes while packages install.

To update later: upload the changed files to GitHub; the app redeploys by itself.

## Switch on AI commentary (optional)

Add `GEMINI_API_KEY = "…"` in the app's Secrets. Without a key every KPI and verified fact still works.
Free Gemini keys may allow Google to use prompts to improve its products — use a paid key before loading real customer data.

## Supabase (optional now, required for real customers)

1. supabase.com → New project (choose a region near your users) → save the database password in a password manager.
2. SQL Editor → paste and run `supabase/migrations/0001_schema.sql`, then `0002_rls.sql`.
3. Project Settings → Database → **Connection string → Session pooler** → copy the URI.
4. On your computer: `set DATABASE_URL=<that URI>` then `python scripts/load_demo_data.py`.
5. In Streamlit Secrets add `DATABASE_URL = "<that URI>"`.

Honest note: in this module the app connects with the database owner account, so tenant separation is enforced by the
application (every query filters by organisation). Row Level Security is already defined and tested, and becomes
the per-user guarantee when Supabase sign-in is added in Phase 2.

## Tests

```
pip install -r requirements-dev.txt
pytest
```

## Health score (summary)

Site score = Σ(KPI weight × RAG points) ÷ Σ(weights of KPIs that have data). Points Green 100 / Amber 60 / Red 20;
status ≥ 90 Green, ≥ 75 Amber, else Red; below 60 % data coverage → “Insufficient data”. Missing data is never
counted as poor performance. A selection covering several sites shows the average of its site scores.
All of these values are configurable per organisation (`organizations.settings.health`).
