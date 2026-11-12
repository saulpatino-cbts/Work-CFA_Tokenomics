"""Per-account scoping of usage reads. All data is SYNTHETIC TEST DATA."""

import os
import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from conftest import TENANT, make_tenant, reset_database
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text

from cfa_tokenomics import migrate
from cfa_tokenomics.config import Settings, get_settings
from cfa_tokenomics.db import AuditEvent
from cfa_tokenomics.main import create_app
from cfa_tokenomics.tenancy import tenant_session
from cfa_tokenomics.usage import ledger
from cfa_tokenomics.usage.models import AggregateObservation

URL = os.environ.get("CFA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")
ISS, AUD = "https://idp.test", "cfa"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
T = datetime(2026, 1, 1, tzinfo=UTC)
RANGE = {"start": T.isoformat(), "end": (T + timedelta(hours=1)).isoformat()}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("CFA_DATABASE_URL", URL)
    engine = create_engine(URL)
    reset_database(engine)
    migrate.main(["upgrade"])
    make_tenant(engine)
    settings = Settings(
        environment="production",
        oidc_issuer=ISS,
        oidc_audience=AUD,
        database_secret_ref="ref",
        database_url=SecretStr(URL),
        oidc_finance_group="readers",
        bootstrap_admin=f"{ISS}|root",
        default_tenant_id=TENANT,
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.key_provider = lambda _t: KEY.public_key()
    with tenant_session(engine, TENANT) as db:
        for acct, val in (("a", 10.0), ("b", 20.0)):
            ledger.upsert_aggregate(
                db,
                AggregateObservation(
                    "bedrock", acct, "m", "input", T, T + timedelta(minutes=5), "Sum", val
                ),
            )
            ledger.save_checkpoint(db, "bedrock", acct, "c")
        yield TestClient(app), db


def hdr(sub="ann", groups=("readers",)):
    claims = {"iss": ISS, "aud": AUD, "sub": sub, "exp": time.time() + 300, "groups": list(groups)}
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="RS256")}


GRANT = {"issuer": ISS, "subject": "ann", "provider": "bedrock", "account": "a"}


def usage(c, sub="ann", **extra):
    return c.get("/v1/usage", params={**RANGE, **extra}, headers=hdr(sub)).json()


def test_reader_without_grants_sees_nothing(env):
    c, _ = env
    body = usage(c)
    assert body["rows"] == [] and body["freshness"] == []


def test_grant_limits_reader_to_that_account(env):
    c, _ = env
    assert c.put("/v1/admin/grants", json=GRANT, headers=hdr("root", ())).status_code == 204
    body = usage(c)
    assert {r["account"] for r in body["rows"]} == {"a"}
    assert {f["account"] for f in body["freshness"]} == {"a"}


def test_filtering_for_an_ungranted_account_returns_nothing(env):
    c, _ = env
    c.put("/v1/admin/grants", json=GRANT, headers=hdr("root", ()))
    assert usage(c, account="b")["rows"] == []


def test_admin_sees_all_accounts(env):
    c, _ = env
    assert {
        r["account"]
        for r in usage(
            c,
            sub="root",
        )["rows"]
    } == {"a", "b"}


def test_grants_are_per_identity(env):
    c, _ = env
    c.put("/v1/admin/grants", json=GRANT, headers=hdr("root", ()))
    assert usage(c, sub="bob")["rows"] == []


def test_revoke_removes_access(env):
    c, _ = env
    c.put("/v1/admin/grants", json=GRANT, headers=hdr("root", ()))
    r = c.delete("/v1/admin/grants", params=GRANT, headers=hdr("root", ()))
    assert r.status_code == 204
    assert usage(c)["rows"] == []
    assert c.delete("/v1/admin/grants", params=GRANT, headers=hdr("root", ())).status_code == 404


def test_non_admin_cannot_manage_grants(env):
    c, _ = env
    assert c.put("/v1/admin/grants", json=GRANT, headers=hdr("ann")).status_code == 403
    assert c.delete("/v1/admin/grants", params=GRANT, headers=hdr("ann")).status_code == 403


def test_grant_changes_are_audited(env):
    c, db = env
    c.put("/v1/admin/grants", json=GRANT, headers=hdr("root", ()))
    c.delete("/v1/admin/grants", params=GRANT, headers=hdr("root", ()))
    actions = [e.action for e in db.query(AuditEvent).order_by(AuditEvent.id)]
    assert actions == ["grant.add", "grant.remove"]


def test_granting_twice_is_idempotent(env):
    c, _ = env
    for _ in range(2):
        assert c.put("/v1/admin/grants", json=GRANT, headers=hdr("root", ())).status_code == 204
    assert len(usage(c)["rows"]) == 1


def test_migration_0003_downgrades_cleanly(env):
    _, db = env
    migrate.main(["downgrade", "0002"])
    with db.bind.connect() as conn:
        names = {r[0] for r in conn.execute(text("select tablename from pg_tables"))}
    assert "account_grants" not in names and "usage_request_observations" in names
    migrate.main(["upgrade"])
