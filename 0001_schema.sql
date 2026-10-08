-- =============================================================================
-- OpsPulse AI - core schema (PostgreSQL 15+ / Supabase)
-- Run this first in Supabase: SQL Editor -> New query -> paste -> Run.
-- Every business table carries organization_id so tenants are always separable,
-- and composite foreign keys (organization_id, x_id) make it impossible to link a
-- row in one organisation to a unit/KPI/upload that belongs to another.
-- Requires PostgreSQL 15+ (Supabase default).
-- =============================================================================

-- gen_random_uuid() is built into PostgreSQL 13+, no extension needed

-- ---------------------------------------------------------------- tenants & people
create table public.organizations (
    id            uuid primary key default gen_random_uuid(),
    name          text not null check (length(trim(name)) > 0),
    slug          text not null unique check (slug ~ '^[a-z0-9-]{3,60}$'),
    industry      text,
    settings      jsonb not null default '{}'::jsonb,   -- health-score points, hierarchy labels, branding
    is_demo       boolean not null default false,       -- true for synthetic demo tenants
    created_at    timestamptz not null default now()
);

-- One row per Supabase Auth user (id = auth.users.id)
create table public.users (
    id            uuid primary key,
    email         text not null unique,
    full_name     text,
    created_at    timestamptz not null default now()
);

create table public.memberships (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    user_id         uuid not null references public.users(id) on delete cascade,
    role            text not null check (role in ('owner','admin','analyst','manager','viewer')),
    status          text not null default 'active' check (status in ('invited','active','suspended')),
    created_at      timestamptz not null default now(),
    unique (organization_id, user_id),
    unique (organization_id, id)
);
create index memberships_user_idx on public.memberships (user_id);

-- ---------------------------------------------------------------- hierarchy
-- Organization -> Business Unit -> Client/Account -> Process -> Location -> Team
-- unit_type is free text so customers can use their own hierarchy levels.
create table public.organizational_units (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    parent_id       uuid,
    unit_type       text not null check (unit_type ~ '^[a-z_]{2,40}$'),   -- business_unit, client, process, location, team ...
    name            text not null check (length(trim(name)) > 0),
    code            text,
    is_active       boolean not null default true,
    created_at      timestamptz not null default now(),
    unique nulls not distinct (organization_id, parent_id, name),
    unique (organization_id, id),
    -- composite key: a parent must belong to the SAME organisation
    foreign key (organization_id, parent_id)
        references public.organizational_units (organization_id, id) on delete restrict,
    check (parent_id is null or parent_id <> id)
);
create index org_units_org_idx    on public.organizational_units (organization_id);
create index org_units_parent_idx on public.organizational_units (parent_id);

-- Which units a member may see (access includes all descendants of the unit)
create table public.unit_access (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    membership_id   uuid not null,
    unit_id         uuid not null,
    access_level    text not null default 'view' check (access_level in ('view','edit','approve')),
    created_at      timestamptz not null default now(),
    unique (membership_id, unit_id),
    foreign key (organization_id, membership_id) references public.memberships (organization_id, id) on delete cascade,
    foreign key (organization_id, unit_id) references public.organizational_units (organization_id, id) on delete cascade
);
create index unit_access_unit_idx on public.unit_access (unit_id);

-- ---------------------------------------------------------------- KPI studio
-- No free-text formulas are ever executed: calc_type picks one of a fixed set of
-- safe calculations, and the engine applies it to numerator / denominator / value.
create table public.kpi_definitions (
    id                uuid primary key default gen_random_uuid(),
    organization_id   uuid not null references public.organizations(id) on delete cascade,
    code              text not null check (code ~ '^[A-Z0-9_]{2,30}$'),
    name              text not null,
    description       text,
    unit              text not null check (unit in ('percent','seconds','minutes','hours','count','currency','ratio','score')),
    calc_type         text not null check (calc_type in ('direct','ratio')),   -- ratio = numerator / denominator x multiplier
    numerator_label   text,
    denominator_label text,
    multiplier        numeric not null default 1 check (multiplier > 0),
    direction         text not null check (direction in ('higher_better','lower_better')),
    frequency         text not null check (frequency in ('daily','weekly','monthly')),
    aggregation       text not null check (aggregation in ('ratio_of_sums','sum','average','weighted_average','last','min','max')),
    decimals          smallint not null default 1 check (decimals between 0 and 4),
    owner_user_id     uuid references public.users(id) on delete set null,
    is_active         boolean not null default true,
    created_at        timestamptz not null default now(),
    unique (organization_id, code),
    unique (organization_id, id),
    check (calc_type = 'direct' or (numerator_label is not null and denominator_label is not null)),
    check (aggregation <> 'ratio_of_sums' or calc_type = 'ratio')
);

-- Which KPI is tracked for which unit, and its weight in the health score
create table public.kpi_assignments (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    kpi_id          uuid not null,
    unit_id         uuid not null,
    weight          numeric not null default 1 check (weight >= 0),
    effective_from  date not null default current_date,
    effective_to    date,
    created_at      timestamptz not null default now(),
    unique (kpi_id, unit_id, effective_from),
    check (effective_to is null or effective_to >= effective_from),
    foreign key (organization_id, kpi_id) references public.kpi_definitions (organization_id, id) on delete cascade,
    foreign key (organization_id, unit_id) references public.organizational_units (organization_id, id) on delete cascade
);
create index kpi_assign_unit_idx on public.kpi_assignments (unit_id);

-- Targets and RAG thresholds (unit_id null = organisation-wide default)
create table public.kpi_targets (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    kpi_id          uuid not null,
    unit_id         uuid,
    target          numeric not null,
    green_threshold numeric not null,      -- at or better than this = Green
    amber_threshold numeric not null,      -- at or better than this = Amber, worse = Red
    effective_from  date not null default current_date,
    effective_to    date,
    created_at      timestamptz not null default now(),
    unique nulls not distinct (kpi_id, unit_id, effective_from),
    check (effective_to is null or effective_to >= effective_from),
    foreign key (organization_id, kpi_id) references public.kpi_definitions (organization_id, id) on delete cascade,
    foreign key (organization_id, unit_id) references public.organizational_units (organization_id, id) on delete cascade
);
create index kpi_targets_kpi_idx on public.kpi_targets (kpi_id);

-- ---------------------------------------------------------------- data hub
create table public.data_uploads (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    file_name       text not null,
    file_sha256     text not null,
    storage_path    text,                                -- original file kept in Supabase Storage
    row_count       integer not null default 0,
    accepted_rows   integer not null default 0,
    rejected_rows   integer not null default 0,
    status          text not null default 'validated'
                    check (status in ('validated','pending_approval','approved','rejected')),
    errors          jsonb not null default '[]'::jsonb,
    uploaded_by     uuid references public.users(id) on delete set null,
    approved_by     uuid references public.users(id) on delete set null,
    created_at      timestamptz not null default now(),
    unique (organization_id, file_sha256),               -- the same file twice = duplicate
    unique (organization_id, id)
);

create table public.kpi_observations (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    kpi_id          uuid not null,
    unit_id         uuid not null,
    period_type     text not null check (period_type in ('day','week','month')),
    period_start    date not null,
    value           numeric,                             -- direct KPIs, or stored result of a ratio
    numerator       numeric,
    denominator     numeric check (denominator is null or denominator >= 0),
    status          text not null default 'approved' check (status in ('submitted','approved','rejected')),
    source          text not null default 'manual' check (source in ('manual','upload','api','synthetic')),
    upload_id       uuid,
    entered_by      uuid references public.users(id) on delete set null,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    unique (kpi_id, unit_id, period_type, period_start),  -- duplicate detection
    check (value is not null or (numerator is not null and denominator is not null)),
    foreign key (organization_id, kpi_id) references public.kpi_definitions (organization_id, id) on delete cascade,
    foreign key (organization_id, unit_id) references public.organizational_units (organization_id, id) on delete cascade,
    foreign key (organization_id, upload_id) references public.data_uploads (organization_id, id) on delete set null (upload_id)
);
create index kpi_obs_unit_period_idx on public.kpi_observations (unit_id, period_start);
create index kpi_obs_org_kpi_idx     on public.kpi_observations (organization_id, kpi_id, period_start);

-- ---------------------------------------------------------------- reports & AI
create table public.report_templates (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    name            text not null,
    storage_path    text not null,                       -- branded .pptx in Supabase Storage
    slide_mapping   jsonb not null default '{}'::jsonb,
    is_default      boolean not null default false,
    created_by      uuid references public.users(id) on delete set null,
    created_at      timestamptz not null default now(),
    unique (organization_id, id)
);

create table public.generated_reports (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    template_id     uuid,
    review_type     text not null check (review_type in ('weekly','monthly','quarterly','executive')),
    unit_ids        uuid[] not null default '{}',
    period_start    date not null,
    period_end      date not null,
    storage_path    text,
    status          text not null default 'draft' check (status in ('draft','approved')),
    created_by      uuid references public.users(id) on delete set null,
    approved_by     uuid references public.users(id) on delete set null,
    created_at      timestamptz not null default now(),
    check (period_end >= period_start),
    foreign key (organization_id, template_id) references public.report_templates (organization_id, id) on delete set null (template_id)
);

create table public.ai_insights (
    id              uuid primary key default gen_random_uuid(),
    organization_id uuid not null references public.organizations(id) on delete cascade,
    unit_id         uuid,
    period_start    date,
    period_end      date,
    question        text not null,
    facts           jsonb not null default '{}'::jsonb,  -- the verified numbers the AI was given
    explanations    text,                                -- possible explanations (labelled as such)
    recommendations text,
    provider        text not null,
    model           text not null,
    created_by      uuid references public.users(id) on delete set null,
    created_at      timestamptz not null default now(),
    foreign key (organization_id, unit_id) references public.organizational_units (organization_id, id) on delete set null (unit_id)
);
create index ai_insights_org_idx on public.ai_insights (organization_id, created_at desc);

-- ---------------------------------------------------------------- actions
create table public.action_items (
    id               uuid primary key default gen_random_uuid(),
    organization_id  uuid not null references public.organizations(id) on delete cascade,
    unit_id          uuid,
    kpi_id           uuid,
    title            text not null,
    description      text,
    owner_user_id    uuid references public.users(id) on delete set null,
    priority         text not null default 'medium' check (priority in ('low','medium','high','critical')),
    due_date         date,
    status           text not null default 'open' check (status in ('open','in_progress','blocked','done','cancelled')),
    escalation_level smallint not null default 0 check (escalation_level between 0 and 3),
    closure_evidence text,
    closed_at        timestamptz,
    created_by       uuid references public.users(id) on delete set null,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),
    check (status <> 'done' or closure_evidence is not null),
    foreign key (organization_id, unit_id) references public.organizational_units (organization_id, id) on delete set null (unit_id),
    foreign key (organization_id, kpi_id) references public.kpi_definitions (organization_id, id) on delete set null (kpi_id)
);
create index actions_org_status_idx on public.action_items (organization_id, status, due_date);

-- ---------------------------------------------------------------- audit (append-only)
create table public.audit_logs (
    id              bigserial primary key,
    organization_id uuid references public.organizations(id) on delete set null,
    actor_user_id   uuid references public.users(id) on delete set null,
    action          text not null,                       -- insert / update / delete / login / export ...
    entity_type     text not null,
    entity_id       text,
    before_data     jsonb,
    after_data      jsonb,
    created_at      timestamptz not null default now()
);
create index audit_org_time_idx on public.audit_logs (organization_id, created_at desc);

-- keep updated_at current
create or replace function public.touch_updated_at() returns trigger
language plpgsql as $$ begin new.updated_at := now(); return new; end $$;

create trigger kpi_obs_touch before update on public.kpi_observations
    for each row execute function public.touch_updated_at();
create trigger actions_touch before update on public.action_items
    for each row execute function public.touch_updated_at();
