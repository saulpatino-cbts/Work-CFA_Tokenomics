"""Telemetry series, SKU and source dimensions. All data is SYNTHETIC TEST DATA."""

import os
import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from conftest import reset_database
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from cfa_tokenomics import migrate
from cfa_tokenomics.config import Settings, get_settings
from cfa_tokenomics.main import create_app
from cfa_tokenomics.usage import ledger
from cfa_tokenomics.usage.models import AggregateObservation, Quality, RequestObservation

URL = os.environ.get("CFA_TEST_DATABASE_URL")
ISS, AUD = "https://idp.test", "cfa"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
T = datetime(2026, 1, 1, tzinfo=UTC)
RNG = {"start": T.isoformat(), "end": (T + timedelta(hours=6)).isoformat()}


def test_models_reject_unknown_dimensions():
    with pytest.raises(ValueError):
        AggregateObservation("p", "a", "m", "input", T, T + timedelta(hours=1), "Sum", 1.0, sku="x")
    with pytest.raises(ValueError):
        RequestObservation("p", "a", "r", 1, "m", T, source_type="nope")


pytestmark_db = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("CFA_DATABASE_URL", URL)
    engine = create_engine(URL)
    reset_database(engine)
    migrate.main(["upgrade"])
    settings = Settings(
        environment="production",
        oidc_issuer=ISS,
        oidc_audience=AUD,
        database_secret_ref="ref",
        database_url=SecretStr(URL),
        oidc_reader_group="readers",
        bootstrap_admin=f"{ISS}|root",
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.key_provider = lambda _t: KEY.public_key()
    with Session(engine) as db:
        yield TestClient(app), db


def hdr(sub="root", groups=()):
    claims = {"iss": ISS, "aud": AUD, "sub": sub, "exp": time.time() + 300, "groups": list(groups)}
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="RS256")}


def agg(value, hour=0, minutes=60, **kw):
    base = dict(provider="bedrock", account="a", model_id="m", category="input", statistic="Sum")
    return AggregateObservation(
        window_start=T + timedelta(hours=hour),
        window_end=T + timedelta(hours=hour, minutes=minutes),
        value=value,
        **{**base, **kw},
    )


def get(c, **p):
    return c.get("/v1/usage/series", params={**RNG, "category": "input", **p}, headers=hdr())


def points(body, **key):
    for s in body["series"]:
        if all(s["key"].get(k) == v for k, v in key.items()):
            return [(p["t"][11:13], p["value"], p["partial"]) for p in s["points"]]
    return None


@pytestmark_db
def test_models_in_same_source_are_summed_within_a_bucket(env):
    c, db = env
    ledger.upsert_aggregate(db, agg(10.0, model_id="m1"))
    ledger.upsert_aggregate(db, agg(5.0, model_id="m2"))
    body = get(c).json()
    assert points(body, provider="bedrock") == [("00", 15.0, False)]


@pytestmark_db
def test_two_sources_are_separate_series_never_added(env):
    c, db = env
    ledger.upsert_aggregate(db, agg(10.0, source_type="cloud_telemetry"))
    ledger.upsert_aggregate(db, agg(12.0, source_type="vendor_admin_api"))
    body = get(c).json()
    assert points(body, source_type="cloud_telemetry") == [("00", 10.0, False)]
    assert points(body, source_type="vendor_admin_api") == [("00", 12.0, False)]
    assert len(body["series"]) == 2


@pytestmark_db
def test_group_by_model_and_invalid_group(env):
    c, db = env
    ledger.upsert_aggregate(db, agg(10.0, model_id="m1"))
    ledger.upsert_aggregate(db, agg(5.0, model_id="m2"))
    body = get(c, group_by=["model_id"]).json()
    assert points(body, model_id="m1") == [("00", 10.0, False)]
    assert points(body, model_id="m2") == [("00", 5.0, False)]
    assert get(c, group_by=["subject"]).status_code == 422


@pytestmark_db
def test_empty_bucket_has_no_point_and_partial_is_flagged(env):
    c, db = env
    ledger.upsert_aggregate(db, agg(10.0, hour=0))
    ledger.upsert_aggregate(db, agg(4.0, hour=2, quality=Quality.PARTIAL))
    assert points(get(c).json(), provider="bedrock") == [("00", 10.0, False), ("02", 4.0, True)]


@pytestmark_db
def test_unknown_request_values_are_excluded_not_zero(env):
    c, db = env
    ledger.record_request(db, RequestObservation("bedrock", "a", "r1", 1, "m", T, input=7))
    ledger.record_request(db, RequestObservation("bedrock", "a", "r2", 1, "m", T, output=9))
    body = get(c).json()
    assert points(body, source_type="app_routed") == [("00", 7.0, False)]


@pytestmark_db
def test_window_longer_than_bucket_is_counted_and_left_out(env):
    c, db = env
    ledger.upsert_aggregate(db, agg(99.0, minutes=180))
    body = get(c).json()
    assert body["series"] == [] and body["excluded_windows"] == 1


@pytestmark_db
def test_sku_filter_and_sku_grouping(env):
    c, db = env
    ledger.upsert_aggregate(db, agg(10.0, sku="api_on_demand"))
    ledger.upsert_aggregate(db, agg(3.0, sku="api_provisioned"))
    body = get(c, group_by=["provider", "sku"]).json()
    assert points(body, sku="api_on_demand") == [("00", 10.0, False)]
    assert points(body, sku="api_provisioned") == [("00", 3.0, False)]
    assert points(get(c, sku="subscription").json(), provider="bedrock") is None
    assert get(c, sku="bogus").status_code == 422


@pytestmark_db
def test_latest_window_end_marks_what_is_not_yet_reported(env):
    c, db = env
    ledger.upsert_aggregate(db, agg(1.0, hour=3))
    latest = get(c).json()["latest_window_end"]
    assert latest[0]["provider"] == "bedrock" and latest[0]["at"].startswith("2026-01-01T04:00")


@pytestmark_db
def test_series_respects_account_scope(env):
    c, db = env
    ledger.upsert_aggregate(db, agg(10.0, account="a"))
    ledger.upsert_aggregate(db, agg(20.0, account="b"))
    assert get(c, group_by=["account"]).json()["series"].__len__() == 2
    reader = c.get(
        "/v1/usage/series",
        params={**RNG, "category": "input"},
        headers=hdr("ann", ("readers",)),
    )
    assert reader.json()["series"] == []
    c.put(
        "/v1/admin/grants",
        json={"issuer": ISS, "subject": "ann", "provider": "bedrock", "account": "a"},
        headers=hdr(),
    )
    granted = c.get(
        "/v1/usage/series",
        params={**RNG, "category": "input", "group_by": ["account"]},
        headers=hdr("ann", ("readers",)),
    ).json()
    assert [s["key"]["account"] for s in granted["series"]] == ["a"]
    assert granted["latest_window_end"][0]["provider"] == "bedrock"


@pytestmark_db
@pytest.mark.parametrize(
    "params",
    [
        {"category": "bogus"},
        {"bucket": "week"},
        {"bucket": "hour", "end": (T + timedelta(days=8)).isoformat()},
        {"start": "2026-01-01T00:00:00", "end": "2026-01-01T06:00:00"},
        {"end": T.isoformat()},
    ],
)
def test_series_validation(env, params):
    c, _ = env
    q = {**RNG, "category": "input", **params}
    assert c.get("/v1/usage/series", params=q, headers=hdr()).status_code == 422


@pytestmark_db
def test_series_requires_authentication(env):
    c, _ = env
    r = c.get("/v1/usage/series", params={**RNG, "category": "input"})
    assert r.status_code == 401


@pytestmark_db
def test_usage_rows_expose_sku_and_source_and_filter(env):
    c, db = env
    ledger.upsert_aggregate(
        db, agg(10.0, hour=0, minutes=5, sku="api_provisioned", source_type="vendor_admin_api")
    )
    rng = {"start": T.isoformat(), "end": (T + timedelta(hours=1)).isoformat()}
    rows = c.get("/v1/usage", params=rng, headers=hdr()).json()["rows"]
    assert (rows[0]["sku"], rows[0]["source_type"]) == ("api_provisioned", "vendor_admin_api")
    none = c.get("/v1/usage", params={**rng, "sku": "subscription"}, headers=hdr()).json()
    assert none["rows"] == []


@pytestmark_db
def test_migration_0004_keeps_existing_rows_as_unknown_sku(env):
    _, db = env
    ledger.upsert_aggregate(db, agg(10.0))
    migrate.main(["downgrade", "0003"])
    migrate.main(["upgrade"])
    row = db.execute(text("select sku, source_type from usage_aggregate_observations")).one()
    assert tuple(row) == ("unknown", "cloud_telemetry")
