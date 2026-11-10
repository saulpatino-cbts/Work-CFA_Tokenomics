"""Economics HTTP API against real PostgreSQL, as a restricted role. All data is SYNTHETIC and the
figures are illustrative placeholders."""

import os
import time
from decimal import Decimal

import jwt
import pytest
from conftest import ROLE, _as
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from test_alloc_runner import FEB1, JAN1, NOW, file, row

from cfa_tokenomics import store
from cfa_tokenomics.config import Settings, get_settings
from cfa_tokenomics.economics_api import tenant_db
from cfa_tokenomics.focus import importer as imp
from cfa_tokenomics.main import create_app
from cfa_tokenomics.models_econ import Scenario
from cfa_tokenomics.tenancy import tenant_session

URL = os.environ.get("CFA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")
ISS, AUD = "https://idp.test", "cfa"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def hdr(sub="root", groups=()):
    claims = {"iss": ISS, "aud": AUD, "sub": sub, "exp": time.time() + 300, "groups": list(groups)}
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="RS256")}


ADMIN, READER = hdr(), hdr("rita", ["readers"])


class Api:
    def __init__(self, engine):
        self.engine = engine
        self.a, self.b = (store.create_tenant(engine, n, "usd", _as(ROLE)) for n in "AB")
        self.tid = self.a
        settings = Settings(
            environment="production", oidc_issuer=ISS, oidc_audience=AUD, database_secret_ref="r",
            database_url=SecretStr(URL), oidc_reader_group="readers", bootstrap_admin=f"{ISS}|root",
            default_tenant_id=self.a,
        )  # fmt: skip
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: settings

        def scoped():  # the restricted role, so row-level security is really in force
            with tenant_session(engine, self.tid, _as(ROLE)) as db:
                yield db, self.tid

        app.dependency_overrides[tenant_db] = scoped
        app.state.key_provider = lambda _t: KEY.public_key()
        self.c = TestClient(app)

    def session(self, tid=None):
        return tenant_session(self.engine, tid or self.a, _as(ROLE))

    def app(self, name="claims", **kw):
        r = self.c.post(
            "/v1/applications", json={"name": name, "currency": "usd", **kw}, headers=ADMIN
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]


@pytest.fixture
def api(env):
    return Api(env)


def q(v, basis="assumed"):
    return {"value": v, "basis": basis}


def scenario(**over):
    """The worked example from docs/economics/05-calculation-engine.md."""
    body = {
        "currency": "USD", "users": q(100), "adoption": q(1), "interactions_per_user": q(40),
        "tokens_per_interaction": {"input": q(10000), "output": q(2500)},
        "models": [
            {"name": "m", "share": q(1),
             "prices": {"input": q(3, "estimated"), "output": q(15, "estimated")}}
        ],
        "transactions_per_user": q(15), "infra_fixed": q(600, "observed"),
        "supporting_api": q(0, "observed"), "licence": q(200, "observed"), "ops_hours": q(10),
        "ops_rate": q(90), "dev_investment": q(120000), "dev_months": q(24),
        "baseline_hours_per_txn": q("0.5"), "assisted_hours_per_txn": q("0.2"),
        "loaded_rate": q(85), "realization": q("0.7"), "cashability": q("0.25"),
    }  # fmt: skip
    body.update(over)
    return body


# ---- access ----------------------------------------------------------------------------------


def test_unauthenticated_and_unmapped_callers_are_refused(api):
    assert api.c.get("/v1/applications").status_code == 401
    assert api.c.get("/v1/applications", headers=hdr("nobody")).status_code == 403


def test_a_reader_reads_but_cannot_write(api):
    app_id = api.app()
    assert api.c.get("/v1/applications", headers=READER).status_code == 200
    assert api.c.get(f"/v1/applications/{app_id}", headers=READER).status_code == 200
    body = {"name": "x", "currency": "usd"}
    assert api.c.post("/v1/applications", json=body, headers=READER).status_code == 403
    put = api.c.put(
        f"/v1/applications/{app_id}/assumptions/k",
        json={"value": 1, "unit": "u", "basis": "assumed", "rationale": "r"},
        headers=READER,
    )
    assert put.status_code == 403
    ev = api.c.post(
        f"/v1/applications/{app_id}/scenarios/evaluate", json=scenario(), headers=READER
    )
    assert ev.status_code == 403
    assert api.c.post("/v1/allocation/runs", json={}, headers=READER).status_code == 403


def test_unconfigured_tenant_is_refused_not_guessed(env):
    settings = Settings(
        environment="production", oidc_issuer=ISS, oidc_audience=AUD, database_secret_ref="r",
        database_url=SecretStr(URL), bootstrap_admin=f"{ISS}|root",
    )  # fmt: skip
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.key_provider = lambda _t: KEY.public_key()
    c = TestClient(app)
    assert c.get("/v1/applications", headers=ADMIN).status_code == 503
    assert c.get("/v1/applications").status_code == 401  # authentication comes first


# ---- applications and assumptions ------------------------------------------------------------


def test_application_round_trip_and_validation(api):
    app_id = api.app(owner="ann", initial_investment="120000.50", investment_basis="assumed")
    got = api.c.get(f"/v1/applications/{app_id}", headers=ADMIN).json()
    assert got["currency"] == "USD" and Decimal(got["initial_investment"]) == Decimal("120000.50")
    assert [
        a["id"] for a in api.c.get("/v1/applications", headers=ADMIN).json()["applications"]
    ] == [app_id]
    post = lambda body: api.c.post("/v1/applications", json=body, headers=ADMIN).status_code  # noqa: E731
    assert post({"name": "x", "currency": "US"}) == 422
    assert post({"name": "x", "currency": "usd", "initial_investment": 1}) == 422  # no basis
    assert post({"name": "x", "currency": "usd", "surprise": 1}) == 422
    assert post({"name": "", "currency": "usd"}) == 422


def test_money_must_be_exact_not_a_float(api):
    body = {
        "name": "x",
        "currency": "usd",
        "initial_investment": 0.1,
        "investment_basis": "assumed",
    }
    assert api.c.post("/v1/applications", json=body, headers=ADMIN).status_code == 422
    body["initial_investment"] = "0.1"
    assert api.c.post("/v1/applications", json=body, headers=ADMIN).status_code == 201


def test_assumptions_are_versioned_and_need_a_rationale(api):
    app_id = api.app()
    url = f"/v1/applications/{app_id}/assumptions/loaded_rate"
    body = {"value": "85", "unit": "money/hour", "basis": "assumed", "rationale": "finance"}
    assert api.c.put(url, json=body, headers=ADMIN).json()["version"] == 1
    assert api.c.put(url, json={**body, "value": "90"}, headers=ADMIN).json()["version"] == 2
    cur = api.c.get(f"/v1/applications/{app_id}/assumptions", headers=ADMIN).json()
    assert [(a["key"], Decimal(a["value"]), a["version"]) for a in cur["assumptions"]] == [
        ("loaded_rate", 90, 2)
    ]
    hist = api.c.get(url + "/history", headers=READER).json()["history"]
    assert [Decimal(h["value"]) for h in hist] == [85, 90]
    assert hist[0]["author"] == f"{ISS}|root"
    assert api.c.put(url, json={**body, "rationale": "  "}, headers=ADMIN).status_code == 422
    unknown = api.c.put(url, json={**body, "value": None}, headers=ADMIN).json()
    assert unknown["value"] is None  # unknown is carried, not turned into zero
    missing = api.c.get(f"/v1/applications/{app_id}/assumptions/nope/history", headers=ADMIN)
    assert missing.status_code == 404


def test_writes_leave_audit_events(api):
    api.app("audited")
    from cfa_tokenomics.db import AuditEvent

    with api.session() as db:
        acts = db.scalars(select(AuditEvent.action).where(AuditEvent.actor == f"{ISS}|root")).all()
    assert "application.create" in acts


# ---- scenarios and explain -------------------------------------------------------------------


def test_scenario_reproduces_the_worked_example_and_is_explainable(api):
    app_id = api.app()
    r = api.c.post(f"/v1/applications/{app_id}/scenarios/evaluate", json=scenario(), headers=ADMIN)
    assert r.status_code == 200, r.text
    res = r.json()["results"]
    assert res["ai_cost"]["value"] == "270" and res["tca"]["value"] == "6970"
    assert res["run_cost"]["value"] == "1970"
    assert res["tca"]["basis"] == "assumed"  # the weakest basis wins, never upgraded
    tree = api.c.get(f"/v1/explain/{res['tca']['id']}", headers=READER).json()
    assert tree["id"] == res["tca"]["id"] and tree["value"] == "6970"
    assert len(tree["inputs"]) >= 5

    def leaves(n):
        return [n] if not n["inputs"] else [x for i in n["inputs"] for x in leaves(i)]

    assert {x["formula"] for x in leaves(tree)} == {"input"}  # reaches the raw inputs
    assert "observed" in {x["basis"] for x in leaves(tree)}


def test_explain_refuses_other_tenants_junk_and_tampered_nodes(api):
    app_id = api.app()
    node = api.c.post(
        f"/v1/applications/{app_id}/scenarios/evaluate", json=scenario(), headers=ADMIN
    ).json()["results"]["tca"]["id"]
    assert api.c.get(f"/v1/explain/{node}", headers=ADMIN).status_code == 200
    for junk in ("zz", "../x", "0" * 16, "A" * 16):
        assert api.c.get(f"/v1/explain/{junk}", headers=ADMIN).status_code == 404
    api.tid = api.b  # same caller, the other tenant: indistinguishable from absent
    assert api.c.get(f"/v1/explain/{node}", headers=ADMIN).status_code == 404
    api.tid = api.a
    with api.engine.begin() as c:  # owner edits a stored node behind the application's back
        from sqlalchemy import text

        c.execute(text("alter table calculation_nodes disable trigger all"))
        c.execute(text("update calculation_nodes set value = 1 where id = :i"), {"i": node})
        c.execute(text("alter table calculation_nodes enable trigger all"))
    assert api.c.get(f"/v1/explain/{node}", headers=ADMIN).status_code == 500


def test_scenario_input_errors_are_422_not_500(api):
    app_id = api.app()
    url = f"/v1/applications/{app_id}/scenarios/evaluate"
    ev = lambda b: api.c.post(url, json=b, headers=ADMIN).status_code  # noqa: E731
    assert ev(scenario(users=q(1.5))) == 422  # float
    assert ev(scenario(currency="EUR")) == 422  # not the application's currency
    bad_shares = [{"name": "m", "share": q("0.5"), "prices": {"input": q(1), "output": q(1)}}]
    assert ev(scenario(models=bad_shares)) == 422  # shares do not sum to 1
    no_price = [{"name": "m", "share": q(1), "prices": {"input": q(1)}}]
    assert ev(scenario(models=no_price)) == 422  # a missing price is not zero
    assert ev(scenario(sensitivity={"users": ["1", "2"], "nope": ["1", "2"]})) == 422
    assert ev(scenario(sensitivity={"users": ["1", "2"]}, sensitivity_output="nothing")) == 422
    assert ev({**scenario(), "surprise": 1}) == 422
    assert api.c.post(
        "/v1/applications/00000000-0000-0000-0000-000000000000/scenarios/evaluate",
        json=scenario(), headers=ADMIN,
    ).status_code == 404  # fmt: skip


def test_unknown_input_makes_the_result_unknown_not_zero(api):
    app_id = api.app()
    r = api.c.post(
        f"/v1/applications/{app_id}/scenarios/evaluate",
        json=scenario(licence=q(None, "observed")), headers=ADMIN,
    )  # fmt: skip
    res = r.json()["results"]
    assert res["tca"]["value"] is None and res["tca"]["status"] == "unknown"
    assert res["ai_cost"]["value"] == "270"  # what is known stays known


def test_tornado_ranks_drivers_and_scenarios_can_be_saved(api):
    app_id = api.app()
    body = scenario(
        sensitivity={"users": ["50", "200"], "tokens_per_interaction.input": ["5000", "20000"]},
        sensitivity_output="ai_cost", save_as="Baseline", kind="baseline",
    )  # fmt: skip
    r = api.c.post(f"/v1/applications/{app_id}/scenarios/evaluate", json=body, headers=ADMIN).json()
    swings = [(t["path"], t["swing"]) for t in r["tornado"]]
    assert swings[0][0] == "users"  # 4x users beats 4x tokens/interaction on input only
    assert Decimal(swings[0][1]) >= Decimal(swings[1][1])
    assert r["tornado"][0]["low"]["basis"] == "assumed"
    with api.session() as db:
        assert db.scalar(select(func.count()).select_from(Scenario)) == 1


# ---- allocation ------------------------------------------------------------------------------


def test_allocation_through_the_api_matches_the_engine(api):
    claims, search = api.app("claims"), api.app("search")
    with api.session() as db:
        cid = imp.get_or_create_manual_connector(db, api.a)
        imp.import_focus_file(
            db, api.a, cid, "f.csv",
            file(row("100.00", 1, tags={"app": "claims"}), row("50.00", 2)),
            declared_version="1.2", now=NOW,
        )  # fmt: skip
    rule = {"name": "claims", "priority": 10, "method": "direct",
            "params": {"application_id": claims}, "conditions": [
                {"field": "tag:app", "op": "eq", "value": "claims"}]}  # fmt: skip
    assert api.c.put("/v1/allocation/rules/by-tag", json=rule, headers=ADMIN).json()["version"] == 1
    fallback = {"name": "rest", "priority": 99, "method": "direct",
                "params": {"application_id": search}}  # fmt: skip
    assert api.c.put("/v1/allocation/rules/rest", json=fallback, headers=ADMIN).status_code == 200
    run = api.c.post(
        "/v1/allocation/runs",
        json={"window_start": JAN1.isoformat(), "window_end": FEB1.isoformat()}, headers=ADMIN,
    )  # fmt: skip
    assert run.status_code == 201 and run.json()["status"] == "succeeded", run.text
    again = api.c.post(
        "/v1/allocation/runs",
        json={"window_start": JAN1.isoformat(), "window_end": FEB1.isoformat()}, headers=ADMIN,
    ).json()  # fmt: skip
    assert again["status"] == "unchanged"
    s = api.c.get("/v1/allocation/summary", headers=READER).json()["summaries"]
    assert len(s) == 1 and s[0]["currency"] == "USD"
    assert Decimal(s[0]["total_effective"]) == 150
    assert Decimal(s[0]["allocated_effective"]) == 150 and Decimal(s[0]["coverage"]) == 1


def test_allocation_input_errors_and_cross_tenant_rules(api):
    claims = api.app("claims")
    put = lambda key, body: api.c.put(f"/v1/allocation/rules/{key}", json=body, headers=ADMIN)  # noqa: E731
    ok = {"name": "n", "priority": 1, "method": "direct", "params": {"application_id": claims}}
    assert put("k", ok).status_code == 200
    assert put("k", {**ok, "method": "magic"}).status_code == 422
    assert put("k", {**ok, "params": {}}).status_code == 422
    ghost = {**ok, "params": {"application_id": "00000000-0000-0000-0000-000000000001"}}
    assert put("k", ghost).status_code == 422
    api.tid = api.b  # tenant B cannot name tenant A's application
    assert put("k2", ok).status_code == 422
    drv = {
        "application_id": claims, "period_start": JAN1.isoformat(), "period_end": FEB1.isoformat(),
        "value": "10", "basis": "assumed", "source": "test",
    }  # fmt: skip
    post = lambda body, key="k": api.c.post(  # noqa: E731
        f"/v1/allocation/rules/{key}/drivers", json=body, headers=ADMIN
    )
    assert post(drv).status_code == 404  # B has no such application
    api.tid = api.a
    assert post(drv).status_code == 201
    assert post({**drv, "period_end": drv["period_start"]}).status_code == 422
    assert post({**drv, "value": 1.5}).status_code == 422
    run = api.c.post(
        "/v1/allocation/runs",
        json={"window_start": FEB1.isoformat(), "window_end": JAN1.isoformat()}, headers=ADMIN,
    )  # fmt: skip
    assert run.status_code == 422
