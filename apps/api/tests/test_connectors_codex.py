"""The Codex and ChatGPT Enterprise connector against a fake Daily Usage API built from the synthetic
samples. No network and no real key: the key is an obviously fake value in an environment variable."""

import json
import os
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from conftest import app, two_tenants
from sqlalchemy import text

from cfa_tokenomics import admin
from cfa_tokenomics.connectors import codex as cx_
from cfa_tokenomics.connectors import costexport as ce
from cfa_tokenomics.connectors.paged import SourceError
from cfa_tokenomics.focus.parse import parse_focus_csv
from cfa_tokenomics.samples.generate import build_all

URL = os.environ.get("CFA_TEST_DATABASE_URL")
ENV = "TEST_OPENAI_ADMIN_KEY"
FAKE_KEY = "fake-openai-admin-key-not-real"
SAMPLES = build_all()
RAW = json.loads(
    SAMPLES["openai/daily_usage_workspace.json"]
)  # plain floats, as written to the wire
WORKSPACE = json.loads(
    SAMPLES["openai/daily_usage_workspace.json"], parse_float=Decimal
)  # as the client parses it
PER_USER = json.loads(SAMPLES["openai/daily_usage_per_user.json"])
NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)
SCOPE = {"credential_ref": f"env:{ENV}", "workspace_id": "ws-example-0001", "lookback_days": 60}
needs_db = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv(ENV, FAKE_KEY)


def cfg(**kw):
    return cx_.parse_scope({**SCOPE, **kw})


class Server:
    """A fake Daily Usage endpoint: rows inside the requested window, a few per page, every request recorded.
    Bodies are written with plain json.dumps so numbers are plain JSON numbers, as the real API sends them."""

    def __init__(self, doc=RAW, page=15):
        self.doc, self.page, self.requests, self.fail = doc, page, [], []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail:
            return httpx.Response(self.fail.pop(0), json={"error": f"echo {FAKE_KEY}"})
        q = request.url.params
        lo, hi = int(q["start_time"]), int(q["end_time"])
        rows = [r for r in self.doc["data"] if lo <= r["start_time"] and r["end_time"] <= hi]
        off = int(q["page"][1:]) if "page" in q else 0
        more = off + self.page < len(rows)
        body = {
            "object": "page",
            "data": rows[off : off + self.page],
            "has_more": more,
            "next_page": f"p{off + self.page}" if more else None,
        }
        return httpx.Response(
            200, content=json.dumps(body).encode(), headers={"content-type": "application/json"}
        )

    def client(self) -> cx_.Client:
        http = httpx.Client(base_url=cx_.BASE_URL, transport=httpx.MockTransport(self.handler))
        return cx_.Client(SCOPE["credential_ref"], http=http, sleep=lambda s: None, min_interval=0)


# ---- configuration -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scope",
    [
        {}, {"credential_ref": f"env:{ENV}"},  # a workspace id is required
        {**SCOPE, "workspace_id": "has space"}, {**SCOPE, "workspace_id": ""},
        {"credential_ref": "sk-admin-literal", "workspace_id": "w"},  # a key where a reference belongs
        {**SCOPE, "api_key": "x"}, {**SCOPE, "base_url": "https://evil.example"},
        {**SCOPE, "mode": "per_user"}, {**SCOPE, "mode": "Aggregate"},
        {**SCOPE, "lookback_days": 0}, {**SCOPE, "final_after_days": 3}, {**SCOPE, "final_after_days": 91},
    ],
)  # fmt: skip
def test_bad_secret_or_unbuilt_settings_are_refused(scope):
    with pytest.raises(ce.ConfigError):
        cx_.parse_scope(scope)


def test_defaults():
    c = cx_.parse_scope({"workspace_id": "w1"}, f"env:{ENV}")
    assert (c.mode.value, c.lookback_days, c.final_after_days, c.billing_account_id) == (
        "aggregate",
        35,
        30,
        "openai-chatgpt-enterprise",
    )
    assert cx_.BASE_URL == "https://api.chatgpt.com/v1" and "base_url" not in cx_._ALLOWED


# ---- the client ----------------------------------------------------------------------------------------


def test_requests_ask_for_workspace_rows_only_use_a_bearer_key_and_page():
    srv = Server(page=4)
    start, end = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)
    rows, refreshed = srv.client().get_all(
        cx_.PATH.format(workspace_id="ws-example-0001"), cx_._params(start, end)
    )
    assert len(rows) == len(RAW["data"]) and refreshed is None
    first = srv.requests[0]
    assert (
        first.headers["authorization"] == f"Bearer {FAKE_KEY}"
        and first.url.path == "/v1/analytics/workspaces/ws-example-0001/usage"
    )
    q = first.url.params
    assert (
        q["group"] == "workspace"
        and "user_ids" not in q
        and "group_ids" not in q
        and "include" not in q
    )
    assert (
        q["start_time"] == str(int(start.timestamp()))
        and q["end_time"] == str(int(end.timestamp()))
        and q["limit"] == "1000"
    )
    assert srv.requests[1].url.params["page"] == "p4" and len(srv.requests) == -(-len(rows) // 4)


def test_money_numbers_are_parsed_as_exact_decimals_not_floats():
    body = '{"object":"page","data":[{"x":0.1234567890123456789,"y":1e2}],"has_more":false,"next_page":null}'
    http = httpx.Client(
        base_url=cx_.BASE_URL,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body.encode())),
    )
    rows, _ = cx_.Client(
        SCOPE["credential_ref"], http=http, sleep=lambda s: None, min_interval=0
    ).get_all("/x", [])
    assert rows[0]["x"] == Decimal("0.1234567890123456789") and isinstance(
        rows[0]["x"], Decimal
    )  # a float would lose digits


def test_a_rejected_key_is_reported_without_echoing_it():
    srv = Server()
    srv.fail = [401]
    with pytest.raises(SourceError) as e:
        srv.client().get_all(
            "/analytics/workspaces/w/usage",
            cx_._params(datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 2, tzinfo=UTC)),
        )
    assert FAKE_KEY not in str(e.value) and "OpenAI" in str(e.value) and "401" in str(e.value)
    assert FAKE_KEY not in repr(srv.client())


# ---- parsing and mapping --------------------------------------------------------------------------------


def parse(doc=None):
    return cx_.parse_days((doc or WORKSPACE)["data"])


def test_workspace_rows_parse_into_model_slices_and_the_sample_reconciles():
    days = parse()
    assert len(days) == len(WORKSPACE["data"]) and all(
        d.end - d.start == (d.end - d.start).__class__(days=1) for d in days
    )
    for d, row in zip(days, WORKSPACE["data"], strict=True):
        credits = sum((s.credits or 0 for s in d.slices), Decimal(0))
        assert credits == Decimal(
            str(row["totals"]["credits"] or 0)
        )  # the slices add back to the day's totals
        usd = sum((s.usd or 0 for s in d.slices), Decimal(0))
        assert usd == Decimal(str(row["totals"]["cost_usd"] or 0))


def test_person_level_rows_are_refused_in_aggregate_mode():
    with pytest.raises(SourceError, match="person-level"):
        cx_.parse_days(PER_USER["data"][:3])
    row = json.loads(json.dumps(RAW["data"][0]), parse_float=Decimal)
    row["actor"] = {"type": "ACCOUNT_USER", "user_id": "u", "email": "a@example.test"}
    with pytest.raises(SourceError, match="person-level"):
        cx_.parse_days([row])


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(start_time=r["start_time"] + 5), lambda r: r.update(end_time=r["start_time"] + 3600),
    lambda r: r.update(start_time="x"), lambda r: r.pop("totals"), lambda r: r["totals"].update(credits=-1),
    lambda r: r["totals"].update(credits=True), lambda r: r["totals"].update(text_output_tokens=1.5),
    lambda r: r.update(models=[{"credits": 1}]), lambda r: r.update(models="x"),
])  # fmt: skip
def test_malformed_rows_are_errors(mutate):
    row = json.loads(json.dumps(RAW["data"][0]), parse_float=Decimal)
    mutate(row)
    with pytest.raises(SourceError):
        cx_.parse_days([row])


def test_the_same_day_twice_is_an_error():
    with pytest.raises(SourceError, match="twice"):
        cx_.parse_days([WORKSPACE["data"][0], WORKSPACE["data"][0]])


def row_of(totals, models=None, day=1790812800):
    return {"object": "workspace.usage.result", "start_time": day, "end_time": day + 86400, "user_id": None, "actor": None,
            "totals": totals, "clients": [], **({"models": models} if models is not None else {})}  # fmt: skip


def test_what_the_totals_hold_beyond_the_model_rows_is_kept_as_an_unattributed_slice():
    D = Decimal
    day = row_of(
        {
            "chats": 1,
            "messages": 1,
            "credits": D("10"),
            "estimated_cost_usd": D("0.40"),
            "text_output_tokens": 500,
        },
        [
            {
                "model": "m",
                "credits": D("6"),
                "estimated_cost_usd": D("0.24"),
                "text_output_tokens": 200,
            }
        ],
    )
    (d,) = cx_.parse_days([day])
    by = {s.model: s for s in d.slices}
    assert (
        by["m"].credits == 6
        and by[None].credits == 4
        and by[None].estimated == D("0.16")
        and by[None].tokens == {"text_output_tokens": 300}
    )


def test_a_day_with_no_model_rows_uses_its_totals_and_nothing_is_invented_when_there_is_no_usage():
    D = Decimal
    (d,) = cx_.parse_days(
        [row_of({"chats": 1, "messages": 1, "credits": D("3"), "estimated_cost_usd": D("0.12")})]
    )
    assert len(d.slices) == 1 and d.slices[0].model is None and d.slices[0].credits == 3
    (idle,) = cx_.parse_days(
        [row_of({"chats": 0, "messages": 0, "credits": None, "cost_usd": None})]
    )
    assert idle.slices == ()


def test_tokens_become_ledger_observations_only_where_the_source_gave_them():
    D = Decimal
    rows = [row_of({"credits": D("1")}, [{"model": "m", "credits": D("1"), "estimated_cost_usd": D("0.04")}]),  # credit-priced: no tokens
            row_of({"credits": None, "cost_usd": D("2.5"), "text_output_tokens": 0, "uncached_text_input_tokens": 100},
                   [{"model": "m", "cost_usd": D("2.5"), "text_output_tokens": 0, "uncached_text_input_tokens": 100}], day=1790899200)]  # fmt: skip
    obs = cx_.usage_observations(cx_.parse_days(rows), "ws")
    assert {(o.category, o.value) for o in obs} == {
        ("output", 0.0),
        ("input", 100.0),
    }  # a reported zero stays zero; absent is absent
    assert all(
        o.provider == "openai_codex" and o.account == "ws" and o.source_type == "vendor_admin_api"
        for o in obs
    )


def test_cost_files_keep_native_usd_and_credit_estimates_apart_and_never_price_credits_without_an_estimate():
    D = Decimal
    rows = [row_of({"credits": D("10"), "estimated_cost_usd": D("0.40"), "cost_usd": D("2.50")},
                   [{"model": "m", "credits": D("10"), "estimated_cost_usd": D("0.40")}, {"model": "n", "credits": None, "cost_usd": D("2.50")}]),
            row_of({"credits": D("5")}, [{"model": "m", "credits": D("5")}], day=1790899200)]  # credits with no estimate  # fmt: skip
    usd, credit, unpriced = cx_.cost_files(cx_.parse_days(rows), cfg())
    assert unpriced == 1
    u = parse_focus_csv(usd, "unknown", 10_000_000)
    c = parse_focus_csv(credit, "unknown", 10_000_000)
    assert not u.rejects and not c.rejects and len(u.rows) == 1 and len(c.rows) == 1
    assert (
        u.rows[0].values["billed_cost"] == D("2.50")
        and u.rows[0].values["sub_account_id"] == "ws-example-0001:usd"
    )
    assert (
        c.rows[0].values["effective_cost"] == D("0.40")
        and c.rows[0].values["sub_account_id"] == "ws-example-0001:credits"
    )
    assert (
        c.rows[0].extensions["x_Credits"] == "10"
        and c.rows[0].extensions["x_Measure"] == "credit_estimate"
    )
    assert (
        u.rows[0].values["service_provider_name"] == "OpenAI"
        and u.rows[0].values["billing_currency"] == "USD"
    )


def test_a_reported_zero_dollar_amount_is_kept_and_a_missing_one_is_not_invented():
    D = Decimal
    usd, credit, unpriced = cx_.cost_files(
        cx_.parse_days(
            [row_of({"credits": None, "cost_usd": D("0")}, [{"model": "m", "cost_usd": D("0")}])]
        ),
        cfg(),
    )
    assert (
        parse_focus_csv(usd, "unknown", 1_000_000).rows[0].values["billed_cost"] == 0
        and credit is None
        and unpriced == 0
    )
    assert cx_.cost_files([], cfg()) == (None, None, 0)


def test_check_reports_each_layer_separately(monkeypatch):
    when = datetime(2026, 10, 31, 12, tzinfo=UTC)  # the three days before are in the sample
    steps = cx_.check(cfg(), Server().client(), when)
    assert [(s.name, s.ok) for s in steps] == [
        ("configuration", True),
        ("credential", True),
        ("access", True),
        ("data", True),
    ]
    quiet = cx_.check(cfg(), Server().client(), NOW)
    assert quiet[-1].name == "data" and not quiet[-1].ok
    monkeypatch.delenv(ENV)
    assert [(s.name, s.ok) for s in cx_.check(cfg(), Server().client(), NOW)] == [
        ("configuration", True),
        ("credential", False),
    ]
    monkeypatch.setenv(ENV, FAKE_KEY)
    srv = Server()
    srv.fail = [403]
    last = cx_.check(cfg(), srv.client(), NOW)[-1]
    assert last.name == "access" and not last.ok and FAKE_KEY not in last.message


# ---- end to end against PostgreSQL, as a restricted role -------------------------------------------------

SAMPLE_USD = sum(Decimal(str(r["totals"]["cost_usd"] or 0)) for r in WORKSPACE["data"])
SAMPLE_EST = sum(
    Decimal(str(r["totals"].get("estimated_cost_usd") or 0)) for r in WORKSPACE["data"]
)
SAMPLE_OUT_TOKENS = sum(r["totals"].get("text_output_tokens", 0) for r in WORKSPACE["data"])
CURRENT = "not exists (select 1 from focus_supersessions s where s.tenant_id = r.tenant_id and s.record_id = r.id)"


class World:
    def __init__(self, env):
        self.env = env
        self.t, self.other = two_tenants(env)
        with app(env, self.t) as db:
            self.cid = cx_.create_connector(db, self.t, "codex-sample", SCOPE)
        self.cfg = cfg()

    def pull(self, server, now=NOW):
        with app(self.env, self.t) as db:
            return cx_.pull(db, self.t, self.cid, self.cfg, server.client(), now)

    def scalar(self, sql, tid=None, **kw):
        with app(self.env, tid or self.t) as db:
            return db.execute(text(sql), kw).scalar()


@pytest.fixture
def w(env):
    return World(env)


def cost_of(w, measure):
    return w.scalar(
        f"select coalesce(sum(effective_cost), 0) from focus_cost_records r where basis = :b and {CURRENT}",
        b=measure,
    )


@needs_db
def test_a_pull_stores_usd_as_observed_and_credit_estimates_as_estimated_and_the_totals_match(w):
    out = w.pull(Server())
    assert {o.status for o in out} <= {"imported", "no_data"} and any(
        o.status == "imported" for o in out
    )
    assert cost_of(w, "observed") == SAMPLE_USD  # the vendor reports native USD
    assert cost_of(w, "estimated") == SAMPLE_EST  # an estimate is never labelled observed
    assert (
        w.scalar(
            "select count(*) from focus_cost_records where basis = 'observed' and right(sub_account_id, 4) <> chr(58) || 'usd'"
        )
        == 0
    )
    assert (
        w.scalar(
            "select count(*) from focus_cost_records where basis = 'estimated' and right(sub_account_id, 8) <> chr(58) || 'credits'"
        )
        == 0
    )
    assert (
        w.scalar(
            "select sum(value) from usage_aggregate_observations where provider = 'openai_codex' and category = 'output'"
        )
        == SAMPLE_OUT_TOKENS
    )
    credits = w.scalar(
        "select coalesce(sum((extensions->>'x_Credits')::numeric), 0) from focus_cost_records where basis = 'estimated'"
    )
    assert credits == sum(
        Decimal(str(r["totals"]["credits"] or 0)) for r in WORKSPACE["data"]
    )  # credits kept exactly


@needs_db
def test_a_second_pull_changes_nothing(w):
    w.pull(Server())
    before = (
        w.scalar("select count(*) from focus_cost_records"),
        w.scalar("select count(*) from usage_aggregate_observations"),
    )
    out = w.pull(Server())
    assert {o.status for o in out} <= {"already_imported", "no_data"}
    assert (
        w.scalar("select count(*) from focus_cost_records"),
        w.scalar("select count(*) from usage_aggregate_observations"),
    ) == before


@needs_db
def test_revising_credit_usage_supersedes_only_the_credit_rows(w):
    w.pull(Server())
    usd_rows = w.scalar("select count(*) from focus_cost_records where basis = 'observed'")
    doc = json.loads(json.dumps(RAW))
    day = next(r for r in doc["data"] if r["totals"]["credits"])
    day["totals"]["credits"] += 100.0
    day["totals"]["estimated_cost_usd"] = round(day["totals"]["estimated_cost_usd"] + 4.0, 2)
    for m in day["models"]:
        if m.get("credits"):
            m["credits"] += 100.0
            m["estimated_cost_usd"] = round(m["estimated_cost_usd"] + 4.0, 2)
    out = w.pull(Server(doc))
    assert any(o.superseded > 0 for o in out)
    assert (
        w.scalar(
            "select count(*) from focus_cost_records r where basis = 'observed' and " + CURRENT
        )
        == usd_rows
    )  # USD rows untouched
    assert cost_of(w, "observed") == SAMPLE_USD
    assert cost_of(w, "estimated") == SAMPLE_EST + Decimal("4.00")
    assert w.scalar("select count(*) from focus_supersessions") > 0  # history is kept


@needs_db
def test_finality_is_provisional_until_the_assumed_correction_window_has_passed(w):
    w.pull(Server(), datetime(2026, 11, 12, 12, tzinfo=UTC))
    assert (
        w.scalar("select count(distinct finality) from ingestion_runs where status = 'succeeded'")
        == 1
    )
    assert (
        w.scalar("select finality from ingestion_runs where status = 'succeeded' limit 1")
        == "provisional"
    )
    w2 = World.__new__(World)
    w2.__dict__.update(w.__dict__)
    w2.cfg = cfg(lookback_days=120)
    with w.env.begin() as c:
        c.execute(text("delete from focus_supersessions"))
    with app(w.env, w.t) as db:
        cx_.pull(db, w.t, w.cid, w2.cfg, Server().client(), datetime(2026, 12, 20, 12, tzinfo=UTC))
    assert (
        w.scalar(
            "select count(*) from ingestion_runs where status = 'succeeded' and finality = 'final'"
        )
        >= 1
    )


@needs_db
def test_a_rejected_key_stores_nothing_and_says_why_without_it(w):
    srv = Server()
    srv.fail = [401]
    out = w.pull(srv)
    assert (
        out[-1].status == "failed"
        and "rejected the credential" in out[-1].detail
        and FAKE_KEY not in out[-1].detail
    )
    assert (
        w.scalar("select count(*) from focus_cost_records") == 0
        and w.scalar("select count(*) from usage_aggregate_observations") == 0
    )


@needs_db
def test_person_rows_are_refused_nothing_personal_is_stored_and_tenants_are_isolated(w):
    out = w.pull(Server(PER_USER))
    assert out[-1].status == "failed" and "person-level" in out[-1].detail
    assert w.scalar("select count(*) from focus_cost_records") == 0
    srv = Server()
    w.pull(srv)
    assert all(r.url.params["group"] == "workspace" for r in srv.requests)
    assert (
        w.scalar(
            "select count(*) from focus_cost_records where extensions::text ~ '@' or tags::text ~ '@'"
        )
        == 0
    )
    assert (
        w.scalar(
            "select count(*) from usage_aggregate_observations where account ~ '@' or model_id ~ '@'"
        )
        == 0
    )
    assert w.scalar("select count(*) from focus_cost_records", tid=w.other) == 0


@needs_db
def test_the_cli_adds_checks_and_runs_a_codex_connector_and_refuses_a_key_or_per_user_mode(
    env, tmp_path, capsys, monkeypatch
):
    t, _ = two_tenants(env)
    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps(SCOPE))
    assert admin.main(["connector-add", "openai_codex", str(t), "cli-codex", str(scope)]) == 0
    assert len(capsys.readouterr().out.strip()) == 36
    for bad, word in (
        ({**SCOPE, "api_key": FAKE_KEY}, "refused"),
        ({**SCOPE, "mode": "per_user"}, "not built yet"),
        ({"credential_ref": f"env:{ENV}"}, "workspace_id"),
    ):
        scope.write_text(json.dumps(bad))
        assert admin.main(["connector-add", "openai_codex", str(t), "cli-bad", str(scope)]) == 1
        err = capsys.readouterr().err
        assert word in err and FAKE_KEY not in err
    with env.connect() as c:
        stored = c.execute(
            text("select credential_ref, scope::text from connectors where name = 'cli-codex'")
        ).one()
    assert stored[0] == f"env:{ENV}" and FAKE_KEY not in stored[1] and "credential" not in stored[1]
    srv = Server()
    monkeypatch.setattr(cx_, "build_client", lambda c: srv.client())
    monkeypatch.setattr(
        cx_,
        "windows",
        lambda c, now=None: [
            (datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC))
        ],
    )
    assert admin.main(["connector-run", str(t), "cli-codex", "--dry-run"]) == 0
    assert "would read 2026-10-01 to 2026-11-01" in capsys.readouterr().out and srv.requests == []
    assert admin.main(["connector-run", str(t), "cli-codex"]) == 0
    assert "imported" in capsys.readouterr().out
    monkeypatch.delenv(ENV)
    assert admin.main(["connector-check", str(t), "cli-codex"]) == 1
    assert "FAIL credential" in capsys.readouterr().out
