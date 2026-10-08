# OpsPulse AI – Phase 1, Module 1 (single-folder edition)

All files sit in ONE folder so they can be uploaded to GitHub in one drag-and-drop.
Streamlit Community Cloud: main file path = app.py.  All data is SYNTHETIC.

Optional look & feel: in GitHub use "Add file → Create new file", name it
.streamlit/config.toml and paste the contents of config.toml.

Secrets (Streamlit → Settings → Secrets), all optional:
  APP_ACCESS_CODE = "your-own-code"
  GEMINI_API_KEY  = "your-gemini-key"
  DATABASE_URL    = "Supabase session-pooler connection string"

Supabase: run 0001_schema.sql then 0002_rls.sql in the SQL Editor; load demo data with
  python load_demo_data.py   (after setting DATABASE_URL on your computer)
