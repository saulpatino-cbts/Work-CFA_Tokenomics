"""Usage read API against real PostgreSQL. All data is SYNTHETIC TEST DATA."""

import os
import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from conftest import TENANT, make_tenant, reset_database
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine

from cfa_tokenomics import migrate
from cfa_tokenomics.config import Settings, get_settings
from cfa_tokenomics.main import create_app
from cfa_tokenomics.tenancy import tenant_session
from cfa_tokenomics.usage import ledger
from cfa_tokenomics.usage.models import AggregateObservation, RequestObservation

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
        yield TestClient(app), db


def hdr(sub="root", groups=()):
    """Defaults to the bootstrap admin (unrestricted scope); scoping is tested separately."""
    claims = {"iss": ISS, "aud": AUD, "sub": sub, "exp": time.time() + 300, "groups": list(groups)}
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="RS256")}


def agg(value, **kw):
    base = dict(provider="bedrock", account="a", model_id="m", category="input", statistic="Sum")
    return AggregateObservation(
        window_start=T, window_end=T + timedelta(minutes=5), value=value, **{**base, **kw}
    )


def req(i, at=T + timedelta(minutes=1), **kw):
    return RequestObservation("bedrock", "a", f"r{i}", 1, "m", at, **kw)


def get(c, params=None, headers=None):
    return c.get("/v1/usage", params=params or RANGE, headers=headers or hdr())


def test_requires_authentication_and_role(env):
    c, _ = env
    assert c.get("/v1/usage", params=RANGE).status_code == 401
    assert get(c, headers=hdr(sub="nobody")).status_code == 403


def test_provider_only_window(env):
    c, db = env
    ledger.upsert_aggregate(db, agg(100.0))
    row = get(c).json()["rows"][0]
    assert (row["status"], row["total"], row["app_observed"]) == ("provider_only", 100.0, None)


def test_reconciled_window_never_adds(env):
    c, db = env
    ledger.upsert_aggregate(db, agg(100.0))
    ledger.record_request(db, req(1, input=30))
    row = get(c).json()["rows"][0]
    assert (row["status"], row["total"], row["unattributed"]) == ("reconciled", 100.0, 70.0)


def test_requests_outside_any_window_are_app_only(env):
    c, db = env
    ledger.record_request(db, req(1, at=T + timedelta(minutes=30), input=7))
    rows = get(c).json()["rows"]
    assert [(r["category"], r["status"], r["total"]) for r in rows] == [("input", "app_only", 7.0)]


def test_unknown_categories_are_omitted_not_zero(env):
    c, db = env
    ledger.record_request(db, req(1, at=T + timedelta(minutes=30), input=7))
    assert {r["category"] for r in get(c).json()["rows"]} == {"input"}


def test_filters_scope_the_result(env):
    c, db = env
    ledger.upsert_aggregate(db, agg(1.0, account="a"))
    ledger.upsert_aggregate(db, agg(2.0, account="b"))
    rows = get(c, params={**RANGE, "account": "b"}).json()["rows"]
    assert [r["account"] for r in rows] == ["b"]


def test_freshness_reports_checkpoint(env):
    c, db = env
    ledger.save_checkpoint(db, "bedrock", "a", "cur")
    assert get(c).json()["freshness"][0]["provider"] == "bedrock"


@pytest.mark.parametrize(
    "params",
    [
        {"start": T.isoformat(), "end": T.isoformat()},
        {"start": T.isoformat(), "end": (T + timedelta(days=40)).isoformat()},
        {"start": "2026-01-01T00:00:00", "end": "2026-01-02T00:00:00"},
    ],
)
def test_range_validation(env, params):
    assert get(env[0], params=params).status_code == 422


def test_missing_range_is_rejected(env):
    assert env[0].get("/v1/usage", headers=hdr()).status_code == 422
