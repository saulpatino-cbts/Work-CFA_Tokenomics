"""Shared test helpers."""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from cfa_tokenomics import migrate, store
from cfa_tokenomics.tenancy import app_role_grants_sql, tenant_session

URL = os.environ.get("CFA_TEST_DATABASE_URL")


def reset_database(engine: Engine) -> None:
    """Wipe the public schema so each database test starts from nothing and migrates fresh.

    Test databases only. Robust to new tables, unlike listing them by name."""
    with engine.begin() as conn:
        conn.execute(text("drop schema public cascade"))
        conn.execute(text("create schema public"))


ROLE = "cfa_app_test"
WIDE = "cfa_app_test_wide"


def _as(role):
    return lambda conn: conn.execute(text(f"set local role {role}"))


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("CFA_DATABASE_URL", URL)
    engine = create_engine(URL)
    reset_database(engine)
    migrate.main(["upgrade"])
    with engine.begin() as c:
        for role in (ROLE, WIDE):
            c.execute(
                text(
                    f"do $$ begin if not exists (select from pg_roles where rolname='{role}') "
                    f"then create role {role} nologin nosuperuser nobypassrls; end if; end $$"
                )
            )
        for stmt in app_role_grants_sql(ROLE).split(";"):
            if stmt.strip():
                c.execute(text(stmt))
        # A role with broader grants, to prove row-level security stands on its own.
        for stmt in app_role_grants_sql(WIDE).split(";"):
            if stmt.strip():
                c.execute(text(stmt))
        c.execute(text(f"grant update, delete on value_assumptions, calculation_nodes to {WIDE}"))
    yield engine
    engine.dispose()


def app(engine, tid, role=ROLE):
    return tenant_session(engine, tid, _as(role))


def two_tenants(engine):
    a = store.create_tenant(engine, "A", "usd", _as(ROLE))
    b = store.create_tenant(engine, "B", "usd", _as(ROLE))
    return a, b
