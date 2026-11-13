"""Rehearsal of migration 0008 (tenant isolation of the older tables) on an install that holds data.

`test_legacy_isolation.py` proves the mechanics with one row per table. This adds volume: it builds
an install as it was before tenancy, fills every legacy table with many rows, upgrades, names a
tenant, and checks that no row is lost, duplicated, left without a tenant or hidden from that
tenant. All data is SYNTHETIC. It is NOT a rehearsal on a real client's data (risk R-26 stays open
until one is made on a copy of a real install).

``CFA_REHEARSAL_ROWS`` sets the row count per table (default 20000).
"""

import os
import time

import pytest
from conftest import ROLE, app, two_tenants
from sqlalchemy import text

from cfa_tokenomics import legacy_tenancy, migrate
from cfa_tokenomics.tenancy import app_role_grants_sql

URL = os.environ.get("CFA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")
LEGACY = legacy_tenancy.TABLES
ROWS = int(os.environ.get("CFA_REHEARSAL_ROWS", "20000"))

SEED = {
    "role_assignments": (
        "insert into role_assignments (issuer, subject, role, created_at, created_by) "
        "select 'i', 'u' || g, case when g % 2 = 0 then 'reader' else 'user' end, now(), 'x' "
        "from generate_series(1, :n) g"
    ),
    "account_grants": (
        "insert into account_grants (issuer, subject, provider, account, created_at, created_by) "
        "select 'i', 'u' || g, 'bedrock', 'a' || g, now(), 'x' from generate_series(1, :n) g"
    ),
    "audit_events": (
        "insert into audit_events (at, actor, action, target, detail) "
        "select now(), 'x', 'old', 't' || g, '{}' from generate_series(1, :n) g"
    ),
    "usage_request_observations": (
        "insert into usage_request_observations (source_key, provider, account, model_id, "
        "occurred_at, input_tokens, quality, normalization_version, usage_metadata, sku, "
        "source_type, ingested_at) "
        "select 'bedrock|a|r' || g || '|1', 'bedrock', 'a', 'm', now(), 5, 'reported', '1', "
        "'{}', 'unknown', 'app_routed', now() from generate_series(1, :n) g"
    ),
    "usage_aggregate_observations": (
        "insert into usage_aggregate_observations (provider, account, model_id, category, "
        "window_start, window_end, statistic, value, quality, normalization_version, revision, "
        "sku, source_type, updated_at) "
        "select 'bedrock', 'a', 'm', 'input', now() - make_interval(mins => g + 5), "
        "now() - make_interval(mins => g), 'Sum', 10, 'reported', '1', 1, 'unknown', "
        "'cloud_telemetry', now() from generate_series(1, :n) g"
    ),
    "collection_checkpoints": (
        "insert into collection_checkpoints (provider, account, cursor, updated_at) "
        "select 'bedrock', 'a' || g, 'c', now() from generate_series(1, :n) g"
    ),
}


def regrant(env):
    with env.begin() as c:
        for stmt in app_role_grants_sql(ROLE).split(";"):
            if stmt.strip():
                c.execute(text(stmt))


def count(conn, table, where=""):
    return conn.execute(text(f"select count(*) from {table} {where}")).scalar()


def test_every_row_of_a_populated_old_install_survives_the_upgrade_and_tenant_assignment(env):
    assert set(SEED) == set(LEGACY)  # a new legacy table must be added to this rehearsal
    migrate.main(["downgrade", "0007"])
    with env.begin() as c:
        for table in LEGACY:
            c.execute(text(SEED[table]), {"n": ROWS})
    with env.connect() as c:
        before = {t: count(c, t) for t in LEGACY}
    assert set(before.values()) == {ROWS}

    started = time.perf_counter()
    migrate.main(["upgrade"])
    upgrade_s = time.perf_counter() - started
    regrant(env)

    with env.connect() as c:
        assert legacy_tenancy.unassigned_tables(c) == list(LEGACY)
        assert {t: count(c, t) for t in LEGACY} == before  # the upgrade lost and added nothing
        assert {t: count(c, t, "where tenant_id is null") for t in LEGACY} == before
        roles = c.execute(text("select distinct role from role_assignments")).scalars().all()
        assert set(roles) == {"finance_viewer"}  # 0010 folded user and reader into one role

    tenant, other = two_tenants(env)
    started = time.perf_counter()
    done = legacy_tenancy.assign_legacy_tenant(env, tenant)
    assign_s = time.perf_counter() - started
    assert done == before

    with env.connect() as c:
        assert legacy_tenancy.unassigned_tables(c) == []
        assert {t: count(c, t) for t in LEGACY} == before
        assert {t: count(c, t, "where tenant_id is null") for t in LEGACY} == dict.fromkeys(
            LEGACY, 0
        )
        assert {t: count(c, t, f"where tenant_id = '{tenant}'") for t in LEGACY} == before
    with app(env, tenant) as db:
        assert {t: count(db, t) for t in LEGACY} == before
    with app(env, other) as db:
        assert set({t: count(db, t) for t in LEGACY}.values()) == {0}
    assert legacy_tenancy.assign_legacy_tenant(env, tenant) == {}  # safe to run again

    print(
        f"rehearsal rows_per_table={ROWS} upgrade_seconds={upgrade_s:.2f} "
        f"assign_seconds={assign_s:.2f}"
    )
