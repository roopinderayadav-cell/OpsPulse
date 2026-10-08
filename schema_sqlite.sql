-- OpsPulse AI - local demo database (SQLite).
-- Same table and column names as supabase/migrations/0001_schema.sql so the
-- application code runs unchanged on either database.  UUIDs are stored as text.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE, industry TEXT,
    settings TEXT NOT NULL DEFAULT '{}', is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, full_name TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS memberships (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner','admin','analyst','manager','viewer')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('invited','active','suspended')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, user_id));

CREATE TABLE IF NOT EXISTS organizational_units (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    parent_id TEXT REFERENCES organizational_units(id) ON DELETE RESTRICT,
    unit_type TEXT NOT NULL, name TEXT NOT NULL, code TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS org_units_org_idx ON organizational_units (organization_id);

CREATE TABLE IF NOT EXISTS unit_access (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    membership_id TEXT NOT NULL REFERENCES memberships(id) ON DELETE CASCADE,
    unit_id TEXT NOT NULL REFERENCES organizational_units(id) ON DELETE CASCADE,
    access_level TEXT NOT NULL DEFAULT 'view' CHECK (access_level IN ('view','edit','approve')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (membership_id, unit_id));

CREATE TABLE IF NOT EXISTS kpi_definitions (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    code TEXT NOT NULL, name TEXT NOT NULL, description TEXT,
    unit TEXT NOT NULL CHECK (unit IN ('percent','seconds','minutes','hours','count','currency','ratio','score')),
    calc_type TEXT NOT NULL CHECK (calc_type IN ('direct','ratio')),
    numerator_label TEXT, denominator_label TEXT, multiplier REAL NOT NULL DEFAULT 1,
    direction TEXT NOT NULL CHECK (direction IN ('higher_better','lower_better')),
    frequency TEXT NOT NULL CHECK (frequency IN ('daily','weekly','monthly')),
    aggregation TEXT NOT NULL CHECK (aggregation IN ('ratio_of_sums','sum','average','weighted_average','last','min','max')),
    decimals INTEGER NOT NULL DEFAULT 1, owner_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, code));

CREATE TABLE IF NOT EXISTS kpi_assignments (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    kpi_id TEXT NOT NULL REFERENCES kpi_definitions(id) ON DELETE CASCADE,
    unit_id TEXT NOT NULL REFERENCES organizational_units(id) ON DELETE CASCADE,
    weight REAL NOT NULL DEFAULT 1, effective_from TEXT NOT NULL, effective_to TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (kpi_id, unit_id, effective_from));

CREATE TABLE IF NOT EXISTS kpi_targets (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    kpi_id TEXT NOT NULL REFERENCES kpi_definitions(id) ON DELETE CASCADE,
    unit_id TEXT REFERENCES organizational_units(id) ON DELETE CASCADE,
    target REAL NOT NULL, green_threshold REAL NOT NULL, amber_threshold REAL NOT NULL,
    effective_from TEXT NOT NULL, effective_to TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS data_uploads (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL, file_sha256 TEXT NOT NULL, storage_path TEXT,
    row_count INTEGER NOT NULL DEFAULT 0, accepted_rows INTEGER NOT NULL DEFAULT 0,
    rejected_rows INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'validated',
    errors TEXT NOT NULL DEFAULT '[]', uploaded_by TEXT, approved_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (organization_id, file_sha256));

CREATE TABLE IF NOT EXISTS kpi_observations (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    kpi_id TEXT NOT NULL REFERENCES kpi_definitions(id) ON DELETE CASCADE,
    unit_id TEXT NOT NULL REFERENCES organizational_units(id) ON DELETE CASCADE,
    period_type TEXT NOT NULL CHECK (period_type IN ('day','week','month')),
    period_start TEXT NOT NULL, value REAL, numerator REAL, denominator REAL,
    status TEXT NOT NULL DEFAULT 'approved', source TEXT NOT NULL DEFAULT 'manual',
    upload_id TEXT REFERENCES data_uploads(id) ON DELETE SET NULL, entered_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (kpi_id, unit_id, period_type, period_start));
CREATE INDEX IF NOT EXISTS kpi_obs_org_kpi_idx ON kpi_observations (organization_id, kpi_id, period_start);

CREATE TABLE IF NOT EXISTS report_templates (
    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL, storage_path TEXT NOT NULL, slide_mapping TEXT NOT NULL DEFAULT '{}',
    is_default INTEGER NOT NULL DEFAULT 0, created_by TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS generated_reports (
    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    template_id TEXT, review_type TEXT NOT NULL, unit_ids TEXT NOT NULL DEFAULT '[]',
    period_start TEXT NOT NULL, period_end TEXT NOT NULL, storage_path TEXT,
    status TEXT NOT NULL DEFAULT 'draft', created_by TEXT, approved_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS ai_insights (
    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    unit_id TEXT, period_start TEXT, period_end TEXT, question TEXT NOT NULL,
    facts TEXT NOT NULL DEFAULT '{}', explanations TEXT, recommendations TEXT,
    provider TEXT NOT NULL, model TEXT NOT NULL, created_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE IF NOT EXISTS action_items (
    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    unit_id TEXT, kpi_id TEXT, title TEXT NOT NULL, description TEXT, owner_user_id TEXT,
    priority TEXT NOT NULL DEFAULT 'medium', due_date TEXT, status TEXT NOT NULL DEFAULT 'open',
    escalation_level INTEGER NOT NULL DEFAULT 0, closure_evidence TEXT, closed_at TEXT,
    created_by TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (status <> 'done' OR closure_evidence IS NOT NULL));

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, organization_id TEXT, actor_user_id TEXT,
    action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT,
    before_data TEXT, after_data TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
