"""Tenant-isolation tests for the Supabase migrations.

Runs the real migration files on a throw-away local PostgreSQL (pgserver) with a
small Supabase stub, then signs in as different users and checks what they can
see and change.  Requires:  pip install pgserver "psycopg[binary]" pytest
Run:  pytest tests/db -q
"""
import tempfile
import uuid
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))

U = {k: str(uuid.uuid4()) for k in ("admin_a", "manager_a", "viewer_a", "admin_b", "outsider")}


@pytest.fixture(scope="module")
def db():
    srv = pgserver.get_server(tempfile.mkdtemp(), cleanup_mode="stop")
    conn = psycopg.connect(srv.get_uri(), autocommit=True)
    conn.execute((Path(__file__).parent / "supabase_stub.sql").read_text())
    for m in MIGRATIONS:
        conn.execute(m.read_text())
    seed(conn)
    yield conn
    conn.close()


def seed(c):
    for k, uid in U.items():   # the auth trigger copies them into public.users
        c.execute("insert into auth.users (id, email) values (%s, %s)", (uid, f"{k}@example.test"))
    c.execute("insert into organizations (id, name, slug) values "
              "('00000000-0000-0000-0000-00000000000a','Org A','org-a'),"
              "('00000000-0000-0000-0000-00000000000b','Org B','org-b')")
    A, B = "00000000-0000-0000-0000-00000000000a", "00000000-0000-0000-0000-00000000000b"
    mem = {}
    for key, org, role in [("admin_a", A, "admin"), ("manager_a", A, "manager"),
                           ("viewer_a", A, "viewer"), ("admin_b", B, "admin")]:
        mem[key] = c.execute("insert into memberships (organization_id, user_id, role) values (%s,%s,%s) returning id",
                             (org, U[key], role)).fetchone()[0]

    def unit(org, parent, utype, name):
        return c.execute("insert into organizational_units (organization_id, parent_id, unit_type, name) "
                         "values (%s,%s,%s,%s) returning id", (org, parent, utype, name)).fetchone()[0]
    bu = unit(A, None, "business_unit", "Travel")
    cl = unit(A, bu, "client", "Client X")
    p1 = unit(A, cl, "process", "Refunds")
    p2 = unit(A, cl, "process", "Back Office")
    t1 = unit(A, p1, "team", "Refunds Team 1")
    bb = unit(B, None, "business_unit", "Other company BU")
    pb = unit(B, bb, "process", "Secret process")
    c.execute("insert into unit_access (organization_id, membership_id, unit_id, access_level) values (%s,%s,%s,'edit')",
              (A, mem["manager_a"], p1))
    c.execute("insert into unit_access (organization_id, membership_id, unit_id, access_level) values (%s,%s,%s,'view')",
              (A, mem["viewer_a"], p2))
    ka = c.execute("insert into kpi_definitions (organization_id, code, name, unit, calc_type, numerator_label, "
                   "denominator_label, multiplier, direction, frequency, aggregation) values "
                   "(%s,'SLA','SLA','percent','ratio','Met','Total',100,'higher_better','monthly','ratio_of_sums') "
                   "returning id", (A,)).fetchone()[0]
    kb = c.execute("insert into kpi_definitions (organization_id, code, name, unit, calc_type, direction, frequency, "
                   "aggregation) values (%s,'COST','Cost','currency','direct','lower_better','monthly','sum') "
                   "returning id", (B,)).fetchone()[0]
    for u_, v in [(p1, 91), (p2, 85), (t1, 90)]:
        c.execute("insert into kpi_observations (organization_id, kpi_id, unit_id, period_type, period_start, numerator, "
                  "denominator, value, source) values (%s,%s,%s,'month','2026-01-01',%s,100,%s,'synthetic')",
                  (A, ka, u_, v, v))
    c.execute("insert into kpi_observations (organization_id, kpi_id, unit_id, period_type, period_start, value, source) "
              "values (%s,%s,%s,'month','2026-01-01',12345,'synthetic')", (B, kb, pb))
    c.ids = dict(A=A, B=B, bu=bu, cl=cl, p1=p1, p2=p2, t1=t1, pb=pb, ka=ka, kb=kb)


class As:
    """Run statements as a signed-in user (or anon) inside a rolled-back transaction."""
    def __init__(self, conn, who):
        self.c, self.who = conn, who

    def __enter__(self):
        self.tx = self.c.transaction(force_rollback=True)
        self.tx.__enter__()
        if self.who == "anon":
            self.c.execute("set local role anon")
        else:
            self.c.execute("set local role authenticated")
            self.c.execute("select set_config('request.jwt.claim.sub', %s, true)", (U[self.who],))
        return self

    def q(self, sql, args=()):
        return self.c.execute(sql, args).fetchall()

    def __exit__(self, *exc):
        self.tx.__exit__(*exc)
        return False


def names(rows):
    return sorted(r[0] for r in rows)


def test_admin_sees_only_own_org(db):
    with As(db, "admin_a") as s:
        assert names(s.q("select name from organizations")) == ["Org A"]
        assert len(s.q("select 1 from kpi_observations")) == 3
        assert names(s.q("select code from kpi_definitions")) == ["SLA"]
        assert "Secret process" not in names(s.q("select name from organizational_units"))


def test_other_tenant_sees_nothing_of_org_a(db):
    with As(db, "admin_b") as s:
        assert names(s.q("select name from organizations")) == ["Org B"]
        assert names(s.q("select name from organizational_units")) == ["Other company BU", "Secret process"]
        assert s.q("select value from kpi_observations") == [(12345,)]
        assert s.q("select 1 from memberships where organization_id = %s", (db.ids["A"],)) == []


def test_user_without_membership_sees_nothing(db):
    with As(db, "outsider") as s:
        for t in ("organizations", "organizational_units", "kpi_definitions", "kpi_observations",
                  "memberships", "action_items", "audit_logs"):
            assert s.q(f"select 1 from {t}") == [], t


def test_manager_limited_to_granted_process_and_children(db):
    with As(db, "manager_a") as s:
        # path above the process is visible for navigation, sibling process is not
        assert names(s.q("select name from organizational_units")) == ["Client X", "Refunds", "Refunds Team 1", "Travel"]
        vals = sorted(float(r[0]) for r in s.q("select value from kpi_observations"))
        assert vals == [90.0, 91.0]          # Refunds + its team, NOT Back Office (85)


def test_viewer_cannot_write_data(db):
    with As(db, "viewer_a") as s:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            s.q("insert into kpi_observations (organization_id, kpi_id, unit_id, period_type, period_start, value, "
                "status, entered_by) values (%s,%s,%s,'month','2026-02-01',1,'submitted',%s) returning id",
                (db.ids["A"], db.ids["ka"], db.ids["p2"], U["viewer_a"]))


def test_manager_can_submit_for_own_process_only(db):
    with As(db, "manager_a") as s:
        ok = s.q("insert into kpi_observations (organization_id, kpi_id, unit_id, period_type, period_start, value, "
                 "status, entered_by) values (%s,%s,%s,'month','2026-02-01',92,'submitted',%s) returning id",
                 (db.ids["A"], db.ids["ka"], db.ids["p1"], U["manager_a"]))
        assert len(ok) == 1
    with As(db, "manager_a") as s:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            s.q("insert into kpi_observations (organization_id, kpi_id, unit_id, period_type, period_start, value, "
                "status, entered_by) values (%s,%s,%s,'month','2026-02-01',92,'submitted',%s)",
                (db.ids["A"], db.ids["ka"], db.ids["p2"], U["manager_a"]))


def test_cannot_write_into_another_tenant(db):
    with As(db, "admin_a") as s:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            s.q("insert into kpi_definitions (organization_id, code, name, unit, calc_type, direction, frequency, "
                "aggregation) values (%s,'HACK','x','count','direct','higher_better','daily','sum')", (db.ids["B"],))
    with As(db, "admin_a") as s:
        # own organisation id but a unit that belongs to org B -> blocked by the composite foreign key / RLS
        with pytest.raises((psycopg.errors.ForeignKeyViolation, psycopg.errors.InsufficientPrivilege)):
            s.q("insert into kpi_observations (organization_id, kpi_id, unit_id, period_type, period_start, value, "
                "status, entered_by) values (%s,%s,%s,'month','2026-03-01',1,'submitted',%s)",
                (db.ids["A"], db.ids["ka"], db.ids["pb"], U["admin_a"]))
    with As(db, "admin_a") as s:
        assert s.q("update kpi_observations set value = 0 where organization_id = %s returning id", (db.ids["B"],)) == []


def test_composite_fk_blocks_cross_tenant_links_even_for_service_role(db):
    with db.transaction(force_rollback=True):
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            db.execute("insert into kpi_observations (organization_id, kpi_id, unit_id, period_type, period_start, "
                       "value) values (%s,%s,%s,'month','2026-04-01',1)", (db.ids["A"], db.ids["ka"], db.ids["pb"]))


def test_audit_log_is_append_only_and_records_changes(db):
    with As(db, "admin_a") as s:
        rows = s.q("select entity_type, action from audit_logs")
        assert ("kpi_observations", "insert") in rows
        assert all(r[0] != "Secret process" for r in rows)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            s.q("delete from audit_logs")
    with As(db, "admin_a") as s:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            s.q("update audit_logs set action = 'x'")
    with As(db, "manager_a") as s:
        assert s.q("select 1 from audit_logs") == []          # only admins read the audit trail


def test_admin_cannot_promote_self_or_others_to_owner(db):
    with As(db, "admin_a") as s:
        assert s.q("update memberships set role = 'owner' where user_id = %s returning id", (U["admin_a"],)) == []
    with As(db, "admin_a") as s:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            s.q("update memberships set role = 'owner' where user_id = %s", (U["manager_a"],))


def test_anon_has_no_access(db):
    with As(db, "anon") as s:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            s.q("select * from organizations")


def test_done_action_requires_evidence(db):
    with db.transaction(force_rollback=True):
        with pytest.raises(psycopg.errors.CheckViolation):
            db.execute("insert into action_items (organization_id, title, status) values (%s,'x','done')", (db.ids["A"],))


def test_org_delete_cascades_cleanly(db):
    with db.transaction(force_rollback=True):
        db.execute("delete from organizations where id = %s", (db.ids["B"],))
        assert db.execute("select count(*) from kpi_observations where organization_id = %s",
                          (db.ids["B"],)).fetchone()[0] == 0
