-- =============================================================================
-- OpsPulse AI - Row Level Security (run after 0001_schema.sql)
--
-- Rules
--   * A signed-in user only ever sees rows of organisations they are an ACTIVE member of.
--   * owner / admin / analyst see every unit of their organisation.
--   * manager / viewer see only the units granted in unit_access (and everything below them).
--   * Only owner / admin change configuration (hierarchy, KPIs, targets, members).
--   * audit_logs is append-only for users: no update or delete policy exists.
--   * The anon (not signed-in) role gets nothing.
-- Helper functions are SECURITY DEFINER so they can read memberships without
-- recursive RLS; they only ever answer questions about the CALLING user.
-- =============================================================================

-- ---------------------------------------------------------------- helper functions
create or replace function public.is_member(org uuid)
returns boolean language sql stable security definer set search_path = '' as $$
    select exists (
        select 1 from public.memberships m
        where m.organization_id = org and m.user_id = auth.uid() and m.status = 'active');
$$;

create or replace function public.has_role(org uuid, roles text[])
returns boolean language sql stable security definer set search_path = '' as $$
    select exists (
        select 1 from public.memberships m
        where m.organization_id = org and m.user_id = auth.uid()
          and m.status = 'active' and m.role = any (roles));
$$;

-- true when the caller may read data of this unit (granted on the unit itself or any ancestor)
create or replace function public.can_access_unit(unit uuid, min_level text default 'view')
returns boolean language sql stable security definer set search_path = '' as $$
    with recursive target as (
        select u.id, u.organization_id from public.organizational_units u where u.id = unit
    ), chain as (                       -- the unit and all of its ancestors
        select u.id, u.parent_id from public.organizational_units u where u.id = unit
        union all
        select p.id, p.parent_id from public.organizational_units p join chain c on p.id = c.parent_id
    )
    select exists (
        select 1 from target t join public.memberships m
          on m.organization_id = t.organization_id and m.user_id = auth.uid() and m.status = 'active'
        where (min_level = 'view'  and m.role in ('owner','admin','analyst'))
           or (min_level <> 'view' and m.role in ('owner','admin'))
           or exists (
                select 1 from public.unit_access a join chain c on c.id = a.unit_id
                where a.membership_id = m.id
                  and case min_level
                        when 'view'    then true
                        when 'edit'    then a.access_level in ('edit','approve')
                        when 'approve' then a.access_level = 'approve'
                        else false end));
$$;

-- true when the unit is accessible, or is an ancestor of an accessible unit
-- (managers need to see the path Organisation > BU > Client above their process)
create or replace function public.can_see_unit(unit uuid)
returns boolean language sql stable security definer set search_path = '' as $$
    with recursive below as (
        select u.id from public.organizational_units u where u.id = unit
        union all
        select c.id from public.organizational_units c join below b on c.parent_id = b.id
    )
    select public.can_access_unit(unit)
        or exists (select 1 from below b where b.id <> unit and public.can_access_unit(b.id));
$$;

-- users who share at least one organisation with the caller (for owner / assignee names)
create or replace function public.shares_org_with(other uuid)
returns boolean language sql stable security definer set search_path = '' as $$
    select exists (
        select 1 from public.memberships me join public.memberships them
          on them.organization_id = me.organization_id
        where me.user_id = auth.uid() and me.status = 'active' and them.user_id = other);
$$;

revoke all on function public.is_member(uuid), public.has_role(uuid, text[]),
    public.can_access_unit(uuid, text), public.can_see_unit(uuid), public.shares_org_with(uuid) from public, anon;
grant execute on function public.is_member(uuid), public.has_role(uuid, text[]),
    public.can_access_unit(uuid, text), public.can_see_unit(uuid), public.shares_org_with(uuid) to authenticated;

-- ---------------------------------------------------------------- enable RLS everywhere
alter table public.organizations        enable row level security;
alter table public.users                enable row level security;
alter table public.memberships          enable row level security;
alter table public.organizational_units enable row level security;
alter table public.unit_access          enable row level security;
alter table public.kpi_definitions      enable row level security;
alter table public.kpi_assignments      enable row level security;
alter table public.kpi_targets          enable row level security;
alter table public.data_uploads         enable row level security;
alter table public.kpi_observations     enable row level security;
alter table public.report_templates     enable row level security;
alter table public.generated_reports    enable row level security;
alter table public.ai_insights          enable row level security;
alter table public.action_items         enable row level security;
alter table public.audit_logs           enable row level security;

-- not-signed-in visitors get no table access at all
revoke all on all tables in schema public from anon;
revoke all on all sequences in schema public from anon;

-- ---------------------------------------------------------------- organizations
create policy org_select on public.organizations for select to authenticated
    using (public.is_member(id));
create policy org_update on public.organizations for update to authenticated
    using (public.has_role(id, array['owner','admin'])) with check (public.has_role(id, array['owner','admin']));
-- organisations are created by the onboarding service (service role), never by end users

-- ---------------------------------------------------------------- users
create policy users_select on public.users for select to authenticated
    using (id = auth.uid() or public.shares_org_with(id));
create policy users_update_self on public.users for update to authenticated
    using (id = auth.uid()) with check (id = auth.uid());

-- ---------------------------------------------------------------- memberships
create policy memberships_select on public.memberships for select to authenticated
    using (user_id = auth.uid() or public.has_role(organization_id, array['owner','admin']));
create policy memberships_insert on public.memberships for insert to authenticated
    with check (public.has_role(organization_id, array['owner','admin']) and role <> 'owner');
create policy memberships_update on public.memberships for update to authenticated
    using (public.has_role(organization_id, array['owner','admin']) and user_id <> auth.uid())
    with check (public.has_role(organization_id, array['owner','admin'])
                and (role <> 'owner' or public.has_role(organization_id, array['owner'])));
create policy memberships_delete on public.memberships for delete to authenticated
    using (public.has_role(organization_id, array['owner','admin']) and user_id <> auth.uid() and role <> 'owner');

-- ---------------------------------------------------------------- hierarchy
create policy units_select on public.organizational_units for select to authenticated
    using (public.is_member(organization_id) and public.can_see_unit(id));
create policy units_write on public.organizational_units for all to authenticated
    using (public.has_role(organization_id, array['owner','admin']))
    with check (public.has_role(organization_id, array['owner','admin']));

create policy unit_access_select on public.unit_access for select to authenticated
    using (public.has_role(organization_id, array['owner','admin'])
           or membership_id in (select m.id from public.memberships m where m.user_id = auth.uid()));
create policy unit_access_write on public.unit_access for all to authenticated
    using (public.has_role(organization_id, array['owner','admin']))
    with check (public.has_role(organization_id, array['owner','admin']));

-- ---------------------------------------------------------------- KPI studio (config readable by all members)
create policy kpi_defs_select on public.kpi_definitions for select to authenticated
    using (public.is_member(organization_id));
create policy kpi_defs_write on public.kpi_definitions for all to authenticated
    using (public.has_role(organization_id, array['owner','admin']))
    with check (public.has_role(organization_id, array['owner','admin']));

create policy kpi_assign_select on public.kpi_assignments for select to authenticated
    using (public.can_access_unit(unit_id));
create policy kpi_assign_write on public.kpi_assignments for all to authenticated
    using (public.has_role(organization_id, array['owner','admin']))
    with check (public.has_role(organization_id, array['owner','admin']));

create policy kpi_targets_select on public.kpi_targets for select to authenticated
    using (public.is_member(organization_id) and (unit_id is null or public.can_access_unit(unit_id)));
create policy kpi_targets_write on public.kpi_targets for all to authenticated
    using (public.has_role(organization_id, array['owner','admin']))
    with check (public.has_role(organization_id, array['owner','admin']));

-- ---------------------------------------------------------------- data hub
create policy uploads_select on public.data_uploads for select to authenticated
    using (public.has_role(organization_id, array['owner','admin','analyst']) or uploaded_by = auth.uid());
create policy uploads_insert on public.data_uploads for insert to authenticated
    with check (public.has_role(organization_id, array['owner','admin','analyst','manager'])
                and uploaded_by = auth.uid() and status in ('validated','pending_approval'));
create policy uploads_update on public.data_uploads for update to authenticated
    using (public.has_role(organization_id, array['owner','admin']))
    with check (public.has_role(organization_id, array['owner','admin']));

create policy obs_select on public.kpi_observations for select to authenticated
    using (public.can_access_unit(unit_id));
-- data entry needs edit rights on the unit; new rows always start as 'submitted'
create policy obs_insert on public.kpi_observations for insert to authenticated
    with check (public.can_access_unit(unit_id, 'edit') and status = 'submitted' and entered_by = auth.uid());
-- correcting or approving needs approve rights on the unit
create policy obs_update on public.kpi_observations for update to authenticated
    using (public.can_access_unit(unit_id, 'approve')) with check (public.can_access_unit(unit_id, 'approve'));
create policy obs_delete on public.kpi_observations for delete to authenticated
    using (public.has_role(organization_id, array['owner','admin']));

-- ---------------------------------------------------------------- reports & AI
create policy templates_select on public.report_templates for select to authenticated
    using (public.is_member(organization_id));
create policy templates_write on public.report_templates for all to authenticated
    using (public.has_role(organization_id, array['owner','admin']))
    with check (public.has_role(organization_id, array['owner','admin']));

create policy reports_select on public.generated_reports for select to authenticated
    using (public.is_member(organization_id)
           and (public.has_role(organization_id, array['owner','admin','analyst'])
                or created_by = auth.uid()));
create policy reports_insert on public.generated_reports for insert to authenticated
    with check (public.has_role(organization_id, array['owner','admin','analyst','manager'])
                and created_by = auth.uid() and status = 'draft');
create policy reports_update on public.generated_reports for update to authenticated
    using (public.has_role(organization_id, array['owner','admin']) or (created_by = auth.uid() and status = 'draft'))
    with check (public.has_role(organization_id, array['owner','admin']) or (created_by = auth.uid() and status = 'draft'));

create policy insights_select on public.ai_insights for select to authenticated
    using (public.is_member(organization_id) and (unit_id is null and public.has_role(organization_id, array['owner','admin','analyst'])
                                                  or unit_id is not null and public.can_access_unit(unit_id)
                                                  or created_by = auth.uid()));
create policy insights_insert on public.ai_insights for insert to authenticated
    with check (public.is_member(organization_id) and created_by = auth.uid()
                and (unit_id is null and public.has_role(organization_id, array['owner','admin','analyst'])
                     or unit_id is not null and public.can_access_unit(unit_id)));

-- ---------------------------------------------------------------- actions
create policy actions_select on public.action_items for select to authenticated
    using (public.is_member(organization_id)
           and (owner_user_id = auth.uid()
                or (unit_id is null and public.has_role(organization_id, array['owner','admin','analyst']))
                or (unit_id is not null and public.can_access_unit(unit_id))));
create policy actions_insert on public.action_items for insert to authenticated
    with check (created_by = auth.uid()
                and (public.has_role(organization_id, array['owner','admin','analyst'])
                     or (unit_id is not null and public.can_access_unit(unit_id, 'edit'))));
create policy actions_update on public.action_items for update to authenticated
    using (public.is_member(organization_id)
           and (owner_user_id = auth.uid() or public.has_role(organization_id, array['owner','admin'])
                or (unit_id is not null and public.can_access_unit(unit_id, 'edit'))))
    with check (public.is_member(organization_id));

-- ---------------------------------------------------------------- audit (append-only)
create policy audit_select on public.audit_logs for select to authenticated
    using (public.has_role(organization_id, array['owner','admin']));
create policy audit_insert on public.audit_logs for insert to authenticated
    with check (public.is_member(organization_id) and actor_user_id = auth.uid());
-- deliberately NO update / delete policies, and the privileges are removed too
revoke update, delete, truncate on public.audit_logs from authenticated;

-- ---------------------------------------------------------------- automatic audit trail
-- Records every change to the tables that matter for reproducible KPI results.
create or replace function public.write_audit() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
    rec jsonb := to_jsonb(coalesce(new, old));
begin
    insert into public.audit_logs (organization_id, actor_user_id, action, entity_type, entity_id, before_data, after_data)
    -- the organisation may already be gone when rows are removed by a cascade delete
    values ((select o.id from public.organizations o where o.id = (rec->>'organization_id')::uuid),
            auth.uid(), lower(tg_op), tg_table_name, rec->>'id',
            case when tg_op in ('UPDATE','DELETE') then to_jsonb(old) end,
            case when tg_op in ('INSERT','UPDATE') then to_jsonb(new) end);
    return coalesce(new, old);
end $$;

create trigger audit_memberships  after insert or update or delete on public.memberships          for each row execute function public.write_audit();
create trigger audit_unit_access  after insert or update or delete on public.unit_access          for each row execute function public.write_audit();
create trigger audit_units        after insert or update or delete on public.organizational_units for each row execute function public.write_audit();
create trigger audit_kpi_defs     after insert or update or delete on public.kpi_definitions      for each row execute function public.write_audit();
create trigger audit_kpi_targets  after insert or update or delete on public.kpi_targets          for each row execute function public.write_audit();
create trigger audit_observations after insert or update or delete on public.kpi_observations     for each row execute function public.write_audit();
create trigger audit_uploads      after insert or update or delete on public.data_uploads         for each row execute function public.write_audit();
create trigger audit_actions      after insert or update or delete on public.action_items         for each row execute function public.write_audit();
create trigger audit_reports      after insert or update or delete on public.generated_reports    for each row execute function public.write_audit();

-- ---------------------------------------------------------------- new sign-ups
-- Copies each new Supabase Auth user into public.users (membership is granted separately).
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    insert into public.users (id, email, full_name)
    values (new.id, new.email, new.raw_user_meta_data->>'full_name')
    on conflict (id) do nothing;
    return new;
end $$;

create trigger on_auth_user_created after insert on auth.users
    for each row execute function public.handle_new_user();
