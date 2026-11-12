"""Tenant isolation of the tables that predate tenancy, as a restricted (non-superuser) role.
All data is SYNTHETIC."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from conftest import ROLE, WIDE, _as, app, two_tenants
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from cfa_tokenomics import admin, legacy_tenancy, migrate
from cfa_tokenomics.db import AccountGrant, AuditEvent, RoleAssignment
from cfa_tokenomics.tenancy import app_role_grants_sql, tenant_session
from cfa_tokenomics.usage import ledger
from cfa_tokenomics.usage.models import AggregateObservation, RequestObservation

URL = os.environ.get("CFA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")
T = datetime(2026, 1, 1, tzinfo=UTC)
LEGACY = legacy_tenancy.TABLES


def req(**kw):
    base = dict(provider="bedrock", account="a", request_id="r1", attempt=1, model_id="m")
    return RequestObservation(occurred_at=T, input=5, **{**base, **kw})


def agg(value=10.0):
    return AggregateObservation(
        "bedrock", "a", "m", "input", T, T + timedelta(minutes=5), "Sum", value
    )


def write_everything(db, who="ann"):
    ledger.record_request(db, req())
    ledger.upsert_aggregate(db, agg())
    ledger.save_checkpoint(db, "bedrock", "a", "cur")
    db.add(RoleAssignment(issuer="i", subject=who, role="finance_viewer", created_by="x"))
    db.add(AccountGrant(issuer="i", subject=who, provider="bedrock", account="a", created_by="x"))
    db.add(AuditEvent(actor="x", action="test", target="t", detail={}))
    db.commit()


def counts(db):
    return {t: db.execute(text(f"select count(*) from {t}")).scalar() for t in LEGACY}


def test_a_fresh_install_is_finalized_by_the_migration(env):
    with env.connect() as c:
        assert legacy_tenancy.unassigned_tables(c) == []
        for t in LEGACY:
            assert legacy_tenancy.is_finalized(c, t)


def test_one_tenant_never_sees_the_other_tenants_ledger_roles_grants_or_audit(env):
    a, b = two_tenants(env)
    with app(env, a) as db:
        write_everything(db)
    with app(env, a) as db:
        assert set(counts(db).values()) == {1}
    with app(env, b) as db:
        assert set(counts(db).values()) == {0}
        assert db.get(RoleAssignment, ("i", "ann")) is None


def test_the_same_keys_can_exist_in_two_tenants(env):
    a, b = two_tenants(env)
    for tid in (a, b):  # same request, window, checkpoint, role and grant in each tenant
        with app(env, tid) as db:
            assert ledger.record_request(db, req()) is True
            assert ledger.upsert_aggregate(db, agg()) == "inserted"
            write_everything_rest = (
                db.add(RoleAssignment(issuer="i", subject="ann", role="admin", created_by="x")),
            )
            ledger.save_checkpoint(db, "bedrock", "a", f"cur-{tid}")
            db.commit()
            assert write_everything_rest
    with app(env, a) as db:
        assert ledger.load_checkpoint(db, "bedrock", "a") == f"cur-{a}"
        assert ledger.record_request(db, req()) is False  # a replay inside the same tenant
    with app(env, b) as db:
        assert ledger.load_checkpoint(db, "bedrock", "a") == f"cur-{b}"


def test_a_write_with_no_tenant_is_refused_not_stored_without_an_owner(env):
    with tenant_session(env, None, _as(ROLE)) as db, pytest.raises(DBAPIError):
        ledger.record_request(db, req())
    with (
        Session(env) as plain,
        pytest.raises(DBAPIError),
    ):  # not even a superuser may skip the owner
        ledger.record_request(plain, req())


def test_a_session_cannot_write_a_row_for_another_tenant(env):
    a, b = two_tenants(env)
    with app(env, a) as db, pytest.raises(DBAPIError):
        db.execute(
            text(
                "insert into collection_checkpoints (tenant_id, provider, account) "
                "values (:t, 'x', 'y')"
            ),
            {"t": b},
        )


def test_the_audit_log_is_append_only_for_the_runtime_role(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        db.add(AuditEvent(actor="x", action="one", target="t", detail={}))
        db.commit()
        for stmt in ("update audit_events set action = 'edited'", "delete from audit_events"):
            with pytest.raises(DBAPIError):
                db.execute(text(stmt))
            db.rollback()
    with env.begin() as c:  # even with the privilege, no policy allows it
        c.execute(text(f"grant update, delete on audit_events to {WIDE}"))
    with app(env, a, WIDE) as db:
        assert db.execute(text("update audit_events set action = 'edited'")).rowcount == 0
        assert db.execute(text("delete from audit_events")).rowcount == 0
        db.commit()
    with app(env, a) as db:
        assert db.execute(text("select action from audit_events")).scalar() == "one"


def test_the_ledger_request_table_is_append_only_for_the_runtime_role(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        ledger.record_request(db, req())
        with pytest.raises(DBAPIError):
            db.execute(text("delete from usage_request_observations"))


# ---- installs that already hold data ---------------------------------------------------------


def regrant(env):
    with env.begin() as c:
        for stmt in app_role_grants_sql(ROLE).split(";"):
            if stmt.strip():
                c.execute(text(stmt))


def old_install(env):
    """Roll back to before tenancy and put one row in each legacy table, as an old install would."""
    migrate.main(["downgrade", "0007"])
    with env.begin() as c:
        c.execute(
            text(
                "insert into role_assignments (issuer, subject, role, created_at, created_by) "
                "values ('i','ann','admin', now(), 'x')"
            )
        )
        c.execute(
            text(
                "insert into account_grants (issuer, subject, provider, account, created_at, created_by) "
                "values ('i','ann','bedrock','a', now(), 'x')"
            )
        )
        c.execute(
            text(
                "insert into audit_events (at, actor, action, target, detail) values (now(),'x','old','t','{}')"
            )
        )
        c.execute(
            text(
                "insert into usage_request_observations (source_key, provider, account, model_id, occurred_at, "
                "input_tokens, quality, normalization_version, usage_metadata, sku, source_type, ingested_at) "
                "values ('bedrock|a|r1|1','bedrock','a','m', now(), 5, 'reported','1','{}','unknown','app_routed', now())"
            )
        )
        c.execute(
            text(
                "insert into usage_aggregate_observations (provider, account, model_id, category, window_start, "
                "window_end, statistic, value, quality, normalization_version, revision, sku, source_type, updated_at) "
                "values ('bedrock','a','m','input', now() - interval '5 minutes', now(), 'Sum', 10, 'reported','1',1,"
                "'unknown','cloud_telemetry', now())"
            )
        )
        c.execute(
            text(
                "insert into collection_checkpoints (provider, account, cursor, updated_at) values ('bedrock','a','c', now())"
            )
        )
    migrate.main(["upgrade"])
    regrant(env)


def test_old_rows_stay_invisible_and_the_install_reports_not_ready_until_a_tenant_is_named(env):
    old_install(env)
    with env.connect() as c:
        assert legacy_tenancy.unassigned_tables(c) == list(LEGACY)
    a, _ = two_tenants(env)
    with app(env, a) as db:
        assert set(counts(db).values()) == {0}  # fail closed: nothing guessed, nothing shown
    for (
        t
    ) in LEGACY:  # and a runtime role cannot claim them for itself: no privilege, or no row visible
        with app(env, a) as db:
            try:
                claimed = db.execute(
                    text(f"update {t} set tenant_id = :t where tenant_id is null"), {"t": a}
                ).rowcount
            except DBAPIError:
                claimed = 0
            assert claimed == 0, t
    with env.connect() as c:
        assert all(
            c.execute(text(f"select count(*) from {t} where tenant_id is null")).scalar() == 1
            for t in LEGACY
        )


def test_assigning_a_tenant_moves_every_old_row_and_finalizes(env):
    old_install(env)
    a, b = two_tenants(env)
    done = legacy_tenancy.assign_legacy_tenant(env, a)
    assert done == dict.fromkeys(LEGACY, 1)
    with env.connect() as c:
        assert legacy_tenancy.unassigned_tables(c) == []
    with app(env, a) as db:
        assert set(counts(db).values()) == {1}
        assert ledger.load_checkpoint(db, "bedrock", "a") == "c"
        assert (
            ledger.record_request(db, req(request_id="r1")) is False
        )  # the old request is a replay
    with app(env, b) as db:
        assert set(counts(db).values()) == {0}
    assert legacy_tenancy.assign_legacy_tenant(env, a) == {}  # safe to run again
    with env.begin() as c:  # the old global keys are gone: tenant B can reuse them
        assert (
            c.execute(
                text("select count(*) from pg_policies where policyname = 'legacy_orphans'")
            ).scalar()
            == 0
        )
    with app(env, b) as db:
        assert ledger.record_request(db, req()) is True


def test_an_unknown_tenant_is_refused_and_nothing_changes(env):
    old_install(env)
    with pytest.raises(ValueError, match="no such tenant"):
        legacy_tenancy.assign_legacy_tenant(env, uuid.uuid4())
    with env.connect() as c:
        assert legacy_tenancy.unassigned_tables(c) == list(LEGACY)
        assert (
            c.execute(
                text("select count(*) from role_assignments where tenant_id is null")
            ).scalar()
            == 1
        )


def test_the_admin_command_assigns_and_reports(env, capsys):
    old_install(env)
    a, _ = two_tenants(env)
    assert admin.main(["assign-legacy-tenant", str(a)]) == 0
    out = capsys.readouterr().out
    assert "role_assignments: 1 row(s) assigned" in out
    assert admin.main(["assign-legacy-tenant", str(a)]) == 0
    assert "nothing to assign" in capsys.readouterr().out
    assert admin.main(["assign-legacy-tenant", str(uuid.uuid4())]) == 1


def test_readyz_is_not_ready_without_a_tenant_or_while_legacy_rows_have_none(env):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from cfa_tokenomics.config import Settings, get_settings
    from cfa_tokenomics.main import create_app

    old_install(env)
    a, _ = two_tenants(env)

    def ready(**over):
        settings = Settings(
            environment="development", database_url=SecretStr(URL), allow_rls_bypass=True, **over
        )
        app_ = create_app()
        app_.dependency_overrides[get_settings] = lambda: settings
        return TestClient(app_).get("/readyz")

    r = ready()
    assert r.status_code == 503 and r.json()["database"] == "tenant_not_configured"
    r = ready(default_tenant_id=a)
    assert r.status_code == 503 and r.json()["database"] == "legacy_tenant_unassigned"
    legacy_tenancy.assign_legacy_tenant(env, a)
    assert ready(default_tenant_id=a).status_code == 200


# ---- migrations ------------------------------------------------------------------------------


def test_downgrade_and_upgrade_round_trip_on_a_populated_single_tenant_install(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        write_everything(db)
    migrate.main(["downgrade", "0007"])
    with env.connect() as c:
        cols = c.execute(
            text(
                "select 1 from information_schema.columns where table_name = 'role_assignments' and column_name = 'tenant_id'"
            )
        ).all()
        assert cols == []
        assert c.execute(text("select count(*) from role_assignments")).scalar() == 1
        keys = {
            r[0]
            for r in c.execute(
                text(
                    "select conname from pg_constraint where conname in ('role_assignments_pkey','account_grants_pkey','collection_checkpoints_pkey','uq_aggregate_natural_key','usage_request_observations_source_key_key')"
                )
            )
        }
        assert len(keys) == 5
    migrate.main(["upgrade"])
    with env.connect() as c:
        assert legacy_tenancy.unassigned_tables(c) == list(
            LEGACY
        )  # data present: a tenant must be named


def test_downgrade_refuses_to_merge_tenants_that_share_a_key(env):
    a, b = two_tenants(env)
    for tid in (a, b):
        with app(env, tid) as db:
            ledger.save_checkpoint(db, "bedrock", "a", "c")
    with pytest.raises(Exception):  # noqa: B017 - any database error: the point is that it stops
        migrate.main(["downgrade", "0007"])
    with env.connect() as c:  # still at 0010, nothing half-undone
        assert c.execute(text("select version_num from alembic_version")).scalar() == "0010"


# ---- the production shape: a non-superuser owner, for whom row-level security applies --------

OWNER = "cfa_owner_test"


def as_owner(env):
    """Make a plain role the owner of every table, so FORCE ROW LEVEL SECURITY binds it too."""
    with env.begin() as c:
        c.execute(
            text(
                f"do $$ begin if not exists (select from pg_roles where rolname='{OWNER}') then "
                f"create role {OWNER} nologin nosuperuser nobypassrls; end if; end $$"
            )
        )
        c.execute(text(f"grant usage, create on schema public to {OWNER}"))
        for (t,) in c.execute(
            text("select tablename from pg_tables where schemaname = 'public'")
        ).all():
            c.execute(text(f'alter table "{t}" owner to {OWNER}'))
    return OWNER


def owner_engine(env, role):
    from sqlalchemy import create_engine

    return create_engine(URL, connect_args={"options": f"-c role={role}"})


def test_a_non_superuser_owner_can_claim_old_rows_and_nobody_else_can(env):
    old_install(env)
    role = as_owner(env)
    a, b = two_tenants(env)
    owner = owner_engine(env, role)
    with owner.connect() as c:
        assert not c.execute(
            text("select rolsuper or rolbypassrls from pg_roles where rolname = current_user")
        ).scalar()
        # the owner sees the unassigned rows only because of the owner-only policy
        assert c.execute(text("select count(*) from role_assignments")).scalar() == 1
    done = legacy_tenancy.assign_legacy_tenant(owner, a)
    assert done == dict.fromkeys(LEGACY, 1)
    with app(env, a) as db:
        assert set(counts(db).values()) == {1}
    with app(env, b) as db:
        assert set(counts(db).values()) == {0}
    owner.dispose()


def test_the_migration_itself_finalizes_an_empty_install_when_run_by_a_non_superuser_owner(
    env, monkeypatch
):
    migrate.main(["downgrade", "0007"])
    role = as_owner(env)
    with env.begin() as c:
        c.execute(text(f"grant all on alembic_version to {role}"))
    sep = "&" if "?" in URL else "?"
    monkeypatch.setenv("CFA_DATABASE_URL", f"{URL}{sep}options=-c%20role%3D{role}")
    migrate.main(["upgrade"])
    with env.connect() as c:
        assert legacy_tenancy.unassigned_tables(c) == []


def test_migration_0010_turns_user_and_reader_into_finance_viewer(env):
    """Nobody gains access and nobody keeps write access: user and reader both become read-only."""
    a, _ = two_tenants(env)
    migrate.main(["downgrade", "0009"])
    with env.begin() as c:
        c.execute(text("delete from role_assignments"))
        for who, role in (("a", "admin"), ("u", "user"), ("r", "reader")):
            c.execute(
                text(
                    "insert into role_assignments (issuer, subject, role, created_at, created_by, tenant_id) "
                    "values ('i', :who, :role, now(), 'x', :t)"
                ),
                {"who": who, "role": role, "t": a},
            )
    migrate.main(["upgrade"])
    with env.connect() as c:
        got = dict(c.execute(text("select subject, role from role_assignments")).all())
    assert got == {"a": "admin", "u": "finance_viewer", "r": "finance_viewer"}
    migrate.main(["downgrade", "0009"])
    with env.connect() as c:
        assert (
            c.execute(text("select role from role_assignments where subject = 'u'")).scalar()
            == "reader"
        )
    migrate.main(["upgrade"])
