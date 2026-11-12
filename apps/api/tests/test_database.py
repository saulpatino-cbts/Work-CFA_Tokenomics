"""Database tests run against a real PostgreSQL given CFA_TEST_DATABASE_URL (skipped otherwise)."""

import os
import time

import jwt
import pytest
from conftest import TENANT, make_tenant, reset_database
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from cfa_tokenomics import migrate
from cfa_tokenomics.config import Settings, get_settings
from cfa_tokenomics.db import AuditEvent, RoleAssignment
from cfa_tokenomics.main import create_app
from cfa_tokenomics.tenancy import tenant_session

URL = os.environ.get("CFA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")

ISS, AUD = "https://idp.test", "cfa"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def settings(**over) -> Settings:
    base = dict(
        environment="production",
        oidc_issuer=ISS,
        oidc_audience=AUD,
        database_secret_ref="ref",
        database_url=SecretStr(URL or ""),
        bootstrap_admin=f"{ISS}|root",
        default_tenant_id=TENANT,
    )
    base.update(over)
    return Settings(**base)


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("CFA_DATABASE_URL", URL)
    engine = create_engine(URL)
    reset_database(engine)
    migrate.main(["upgrade"])
    make_tenant(engine)
    with tenant_session(engine, TENANT) as s:
        yield s


def token(sub, groups=()):
    claims = {"iss": ISS, "aud": AUD, "sub": sub, "exp": time.time() + 300, "groups": list(groups)}
    return jwt.encode(claims, KEY, algorithm="RS256")


def api(st):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: st
    app.state.key_provider = lambda _t: KEY.public_key()
    return TestClient(app)


def call(c, method, sub, **kw):
    return c.request(
        method, "/v1/admin/roles", headers={"Authorization": f"Bearer {token(sub)}"}, **kw
    )


def test_migration_roundtrip(db, monkeypatch):
    migrate.main(["downgrade", "base"])
    with db.bind.connect() as c:
        names = {r[0] for r in c.execute(text("select tablename from pg_tables"))}
    assert "role_assignments" not in names
    migrate.main(["upgrade"])


def test_db_constraint_rejects_unknown_role(db):
    with pytest.raises(IntegrityError):
        db.add(RoleAssignment(issuer="i", subject="s", role="root", created_by="x"))
        db.commit()


def test_admin_assigns_role_and_it_takes_effect(db):
    c = api(settings())
    r = call(c, "PUT", "root", json={"issuer": ISS, "subject": "ann", "role": "finance_viewer"})
    assert r.status_code == 204
    ok = c.get("/v1/whoami", headers={"Authorization": f"Bearer {token('ann')}"})
    assert ok.status_code == 200
    # a finance viewer still cannot manage identity
    assert (
        call(c, "PUT", "ann", json={"issuer": ISS, "subject": "x", "role": "admin"}).status_code
        == 403
    )
    ev = db.query(AuditEvent).all()
    assert [(e.action, e.actor) for e in ev] == [("role.assign", f"{ISS}|root")]


def test_unmapped_identity_has_no_access(db):
    assert (
        api(settings())
        .get("/v1/whoami", headers={"Authorization": f"Bearer {token('nobody')}"})
        .status_code
        == 403
    )


def test_last_admin_cannot_be_removed_or_demoted(db):
    c = api(settings())
    call(c, "PUT", "root", json={"issuer": ISS, "subject": "adm", "role": "admin"})
    assert (
        call(
            c, "PUT", "root", json={"issuer": ISS, "subject": "adm", "role": "finance_viewer"}
        ).status_code
        == 409
    )
    assert call(c, "DELETE", "root", params={"issuer": ISS, "subject": "adm"}).status_code == 409
    assert db.get(RoleAssignment, (ISS, "adm")).role == "admin"


def test_second_admin_allows_removal(db):
    c = api(settings())
    for s in ("a1", "a2"):
        call(c, "PUT", "root", json={"issuer": ISS, "subject": s, "role": "admin"})
    assert call(c, "DELETE", "root", params={"issuer": ISS, "subject": "a1"}).status_code == 204


def test_idp_admin_group_is_a_standing_path_so_last_db_admin_removable(db):
    c = api(settings(oidc_admin_group="cfa-admins"))
    call(c, "PUT", "root", json={"issuer": ISS, "subject": "adm", "role": "admin"})
    assert call(c, "DELETE", "root", params={"issuer": ISS, "subject": "adm"}).status_code == 204


def test_remove_missing_is_404(db):
    c = api(settings())
    assert call(c, "DELETE", "root", params={"issuer": ISS, "subject": "ghost"}).status_code == 404


def test_readyz_reflects_database(db):
    # The test database role is a superuser, so opt in to the dev-only bypass explicitly.
    ok = api(settings(allow_rls_bypass=True)).get("/readyz").json()
    assert ok == {"status": "ready", "database": "ok"}
    bad = settings(database_url=SecretStr("postgresql+psycopg://x:y@127.0.0.1:1/none"))
    r = api(bad).get("/readyz")
    assert r.status_code == 503 and r.json()["database"] == "unreachable"


def test_readyz_refuses_a_role_that_bypasses_row_level_security(db):
    """A superuser or BYPASSRLS role silently turns tenant isolation off, so it is not ready."""
    r = api(settings()).get("/readyz")
    assert r.status_code == 503
    assert r.json() == {"status": "not_ready", "database": "role_bypasses_rls"}


def test_readyz_production_without_database_is_503():
    r = api(settings(database_url=None)).get("/readyz")
    assert r.status_code == 503
