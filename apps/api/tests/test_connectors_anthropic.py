"""The Anthropic connector against a fake Admin API built from the synthetic sample sets. No network, no
real key: the key below is an obviously fake value in an environment variable the tests set themselves."""

import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from conftest import app, two_tenants
from sqlalchemy import text

from cfa_tokenomics import admin
from cfa_tokenomics.connectors import anthropic as an
from cfa_tokenomics.connectors import costexport as cx
from cfa_tokenomics.connectors import credentials as cred
from cfa_tokenomics.focus.ai import ai_token_report
from cfa_tokenomics.focus.parse import parse_focus_csv
from cfa_tokenomics.samples.generate import build_all

URL = os.environ.get("CFA_TEST_DATABASE_URL")
ENV = "TEST_ANTHROPIC_ADMIN_KEY"
FAKE_KEY = "fake-admin-key-not-real-0000"
SAMPLES = build_all()
USAGE = json.loads(SAMPLES["anthropic/analytics_usage_by_model.json"])
COST = json.loads(SAMPLES["anthropic/analytics_cost_by_model.json"])
ACTOR = json.loads(SAMPLES["anthropic/analytics_usage_by_actor.json"])
NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)
SCOPE = {"credential_ref": f"env:{ENV}", "lookback_days": 60}


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv(ENV, FAKE_KEY)


def cfg(**kw):
    return an.parse_scope({**SCOPE, **kw})


class Server:
    """A fake of the two analytics endpoints. Serves the sample rows inside the requested window, a few per
    page so paging is exercised, and records every request."""

    def __init__(self, usage=USAGE, cost=COST, refreshed="2026-11-02T04:00:00Z", page=40):
        self.docs = {
            "/v1/organizations/analytics/usage": usage,
            "/v1/organizations/analytics/cost": cost,
        }
        self.refreshed, self.page, self.requests = refreshed, page, []
        self.fail: list[int] = []  # status codes to return before succeeding

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail:
            code = self.fail.pop(0)
            headers = {"retry-after": "0"} if code == 429 else {}
            return httpx.Response(code, headers=headers, json={"error": f"secret echo {FAKE_KEY}"})
        q = request.url.params
        start, end = q["starting_at"], q["ending_at"]
        rows = [
            r
            for r in self.docs[request.url.path]["data"]
            if start <= r["starting_at"] and r["ending_at"] <= end
        ]
        offset = int(q["page"][1:]) if "page" in q else 0
        chunk = rows[offset : offset + self.page]
        more = offset + self.page < len(rows)
        return httpx.Response(200, json={"data": chunk, "has_more": more, "next_page": f"p{offset + self.page}" if more else None,
                                         "data_refreshed_at": self.refreshed})  # fmt: skip

    def client(self, **kw) -> an.Client:
        http = httpx.Client(base_url=an.BASE_URL, transport=httpx.MockTransport(self.handler))
        return an.Client(
            SCOPE["credential_ref"], http=http, sleep=lambda s: None, min_interval=0, **kw
        )


# ---- credentials ----------------------------------------------------------------------------------------


def test_a_credential_reference_resolves_and_its_errors_never_contain_the_value(
    monkeypatch, tmp_path
):
    assert cred.resolve(f"env:{ENV}") == FAKE_KEY
    f = tmp_path / "k"
    f.write_text(FAKE_KEY + "\n")
    assert cred.resolve(f"file:{f}") == FAKE_KEY
    monkeypatch.setenv(ENV, "two words")
    with pytest.raises(cred.CredentialError) as e:
        cred.resolve(f"env:{ENV}")
    assert "two words" not in str(e.value)
    for bad in (
        "",
        "token",
        "env:lower",
        "env:",
        "file:relative/path",
        "file:/a/../b",
        "http://x",
        5,
    ):
        with pytest.raises(cred.CredentialError):
            cred.check_ref(bad)
    monkeypatch.delenv(ENV)
    with pytest.raises(cred.CredentialError, match="empty or not set"):
        cred.resolve(f"env:{ENV}")
    with pytest.raises(cred.CredentialError, match="could not be read"):
        cred.resolve("file:/nonexistent/credential")


# ---- configuration -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scope",
    [
        {},  # no credential reference
        {"credential_ref": "sk-ant-admin01-literal"},  # a key where a reference belongs
        {**SCOPE, "api_key": "x"}, {**SCOPE, "x-api-key": "x"}, {**SCOPE, "base_url": "https://evil.example"},
        {**SCOPE, "mode": "per_user"},  # not built yet
        {**SCOPE, "mode": "per-user"}, {**SCOPE, "mode": "everything"},
        {**SCOPE, "lookback_days": 0}, {**SCOPE, "lookback_days": 366}, {**SCOPE, "lookback_days": True},
        {**SCOPE, "billing_account_id": "has space"},
    ],
)  # fmt: skip
def test_bad_or_secret_or_unbuilt_settings_are_refused(scope):
    with pytest.raises(cx.ConfigError):
        an.parse_scope(scope)


def test_defaults_and_the_credential_ref_may_come_from_the_column():
    c = an.parse_scope({}, f"env:{ENV}")
    assert (c.mode.value, c.lookback_days, c.billing_account_id) == ("aggregate", 35, "anthropic")


def test_windows_are_day_aligned_at_most_31_days_and_stop_before_today():
    w = an.windows(cfg(lookback_days=70), NOW)
    assert w[-1][1] == datetime(2026, 11, 12, tzinfo=UTC) and w[0][0] == datetime(
        2026, 9, 3, tzinfo=UTC
    )
    assert all(b - a <= timedelta(days=31) for a, b in w) and all(
        w[i][1] == w[i + 1][0] for i in range(len(w) - 1)
    )
    early = an.windows(cfg(lookback_days=365), datetime(2026, 2, 1, 5, tzinfo=UTC))
    assert early[0][0] == an.MIN_START  # the API refuses anything earlier


# ---- the HTTP client ----------------------------------------------------------------------------------


def test_requests_carry_the_documented_headers_group_only_by_aggregate_dimensions_and_page():
    srv = Server(page=7)
    rows, refreshed = srv.client().get_all(
        "/v1/organizations/analytics/usage",
        an._params(datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC), False),
    )
    assert len(rows) == len(USAGE["data"]) and refreshed == srv.refreshed
    assert len(srv.requests) == -(-len(rows) // 7)  # one request per page
    first = srv.requests[0]
    assert (
        first.headers["x-api-key"] == FAKE_KEY
        and first.headers["anthropic-version"] == an.API_VERSION
    )
    assert first.headers["anthropic-beta"] == an.BETA
    groups = [v for k, v in first.url.params.multi_items() if k == "group_by[]"]
    assert groups == list(an.USAGE_GROUPS) and "actor" not in groups and "actor_type" not in groups
    assert first.url.params["time_bucket_width"] == "1d" and first.url.params["limit"] == "1000"
    assert "page" not in first.url.params and srv.requests[1].url.params["page"] == "p7"


def test_the_host_is_fixed_so_a_key_cannot_be_sent_elsewhere():
    assert an.BASE_URL == "https://api.anthropic.com"
    assert "base_url" not in an._ALLOWED


def test_a_rate_limit_is_waited_out_and_a_server_error_is_retried_a_bounded_number_of_times():
    srv = Server()
    srv.fail = [429, 503]
    slept = []
    c = srv.client()
    c._sleep = slept.append
    rows, _ = c.get_all(
        "/v1/organizations/analytics/usage",
        an._params(datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC), False),
    )
    assert rows and slept[:2] == [
        0.0,
        2,
    ]  # retry-after 0 from the 429, then 2 seconds of backoff for the 503
    srv2 = Server()
    srv2.fail = [503] * 9
    with pytest.raises(an.SourceError, match="kept refusing"):
        srv2.client().get_all(
            "/v1/organizations/analytics/usage",
            [("starting_at", "2026-10-01T00:00:00Z"), ("ending_at", "2026-10-02T00:00:00Z")],
        )
    assert len(srv2.requests) == an.MAX_ATTEMPTS


def test_a_rejected_credential_is_reported_without_echoing_the_key_or_the_response():
    srv = Server()
    srv.fail = [401]
    with pytest.raises(an.SourceError) as e:
        srv.client().get_all(
            "/v1/organizations/analytics/usage",
            [("starting_at", "2026-10-01T00:00:00Z"), ("ending_at", "2026-10-02T00:00:00Z")],
        )
    assert (
        FAKE_KEY not in str(e.value) and "secret echo" not in str(e.value) and "401" in str(e.value)
    )
    assert FAKE_KEY not in repr(srv.client())


def test_an_expired_cursor_restarts_the_query_but_only_a_few_times():
    class Flaky(Server):
        def handler(self, request):
            if "page" in request.url.params and not getattr(self, "burned", False):
                self.burned = True
                self.requests.append(request)
                return httpx.Response(410, json={})
            return super().handler(request)

    srv = Flaky(page=5)
    rows, _ = srv.client().get_all(
        "/v1/organizations/analytics/usage",
        an._params(datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC), False),
    )
    assert len(rows) == len(USAGE["data"])

    class Always(Server):
        def handler(self, request):
            return (
                httpx.Response(410, json={})
                if "page" in request.url.params
                else super().handler(request)
            )

    with pytest.raises(an.SourceError, match="refreshed"):
        Always(page=5).client().get_all(
            "/v1/organizations/analytics/usage",
            an._params(datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC), False),
        )


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"data": "x", "has_more": False},
        {"data": [], "has_more": "no"},
        {"data": [], "has_more": True, "next_page": None},
    ],
)
def test_unexpected_response_shapes_are_errors_not_guesses(body):
    http = httpx.Client(
        base_url=an.BASE_URL,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)),
    )
    with pytest.raises(an.SourceError):
        an.Client(SCOPE["credential_ref"], http=http, sleep=lambda s: None, min_interval=0).get_all(
            "/v1/organizations/analytics/usage", []
        )


def test_requests_are_paced_under_the_documented_rate_limit():
    srv = Server(page=3)
    slept = []
    c = srv.client()
    c._min_interval, c._sleep = 1.1, slept.append
    c.get_all(
        "/v1/organizations/analytics/usage",
        an._params(datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC), False),
    )
    assert (
        len(srv.requests) > 3 and all(0 < s <= 1.1 for s in slept) and len(slept) >= 3
    )  # 60 per minute is the limit
    assert an.MANIFEST["limits"].startswith("60 requests per minute")


# ---- mapping ------------------------------------------------------------------------------------------


def test_usage_rows_become_ledger_observations_summed_over_tier_speed_and_context():
    usage = an.parse_usage(USAGE["data"])
    obs = an.usage_observations(usage)
    assert {o.category for o in obs} == {"input", "output", "cache_read", "cache_write", "total"}
    assert {(o.provider, o.source_type, o.sku, o.statistic) for o in obs} == {
        ("anthropic", "vendor_admin_api", "unknown", "Sum")
    }
    first = USAGE["data"][0]
    got = {
        o.category: o.value
        for o in obs
        if o.window_start.isoformat().startswith(first["starting_at"][:10])
    }
    u = first["usage"]
    assert (
        got["input"] == u["uncached_input_tokens"]
        and got["cache_read"] == u["cache_read_input_tokens"]
    )
    assert (
        got["cache_write"] == sum(u["cache_creation"].values())
        and got["total"] == u["total_tokens"]
    )
    assert all(o.account == "wrkspc_example0001" and o.model_id == "example-model-a" for o in obs)


def test_person_level_rows_are_refused_in_aggregate_mode_and_nothing_is_read_from_them():
    with pytest.raises(an.SourceError, match="person-level"):
        an.parse_usage(ACTOR["data"])
    leaky = json.loads(json.dumps(USAGE["data"][:1]))
    leaky[0]["group"]["claude_tag_user_id"] = "U0123ABCDEF"
    with pytest.raises(an.SourceError, match="person-level"):
        an.parse_usage(leaky)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r["usage"].update(output_tokens=-1),
        lambda r: r["usage"].update(output_tokens=1.5),
        lambda r: r["usage"].update(output_tokens=True),
        lambda r: r.pop("usage"),
        lambda r: r.pop("group"),
        lambda r: r.update(starting_at="not a date"),
        lambda r: r.update(ending_at="2026-10-02T00:00:00"),
    ],
)
def test_malformed_usage_rows_are_errors(mutate):
    row = json.loads(json.dumps(USAGE["data"][0]))
    mutate(row)
    with pytest.raises(an.SourceError):
        an.parse_usage([row])


def test_a_group_returned_twice_is_an_error_not_a_silent_overwrite():
    with pytest.raises(an.SourceError, match="twice"):
        an.parse_usage([USAGE["data"][0], USAGE["data"][0]])


def test_cost_rows_become_focus_rows_with_cents_converted_exactly_and_tokens_joined():
    usage = an.parse_usage(USAGE["data"])
    data, n = an.cost_csv(COST["data"], usage, cfg())
    assert n == len(COST["data"])
    parsed = parse_focus_csv(data, "unknown", 50_000_000)
    assert not parsed.rejects and len(parsed.rows) == n
    first = COST["data"][0]
    r0 = parsed.rows[0].values
    assert (
        r0["list_cost"] == Decimal(first["cost"]["list_amount"]) / 100
        and r0["billed_cost"] == Decimal(first["cost"]["amount"]) / 100
    )
    assert (
        r0["effective_cost"] == r0["contracted_cost"] == r0["billed_cost"]
        and r0["service_provider_name"] == "Anthropic"
    )
    by_type = {}
    for row in parsed.rows:
        v = row.values
        if v["charge_period_start"].day == 1:
            by_type[row.extensions.get("x_TokenType")] = v
    out = by_type["output_tokens"]
    assert (
        out["consumed_unit"] == "Tokens" and out["sku_price_details"]["TokenDirection"] == "Output"
    )
    assert (
        "TokenCacheAction" not in out["sku_price_details"]
        and out["sku_price_details"]["ModelDeveloper"] == "Anthropic"
    )
    assert by_type["cache_read_input_tokens"]["sku_price_details"]["TokenCacheAction"] == "Read"
    assert (
        by_type["cache_creation.ephemeral_5m_input_tokens"]["sku_price_details"]["TokenCacheAction"]
        == "Write"
    )
    assert by_type["uncached_input_tokens"]["sku_price_details"]["TokenCacheAction"] == "Uncached"
    assert all(row.extensions.get("x_BilledCostIsPreCredit") == "true" for row in parsed.rows)


def test_a_non_usd_or_non_decimal_amount_is_an_error_never_converted_or_guessed():
    usage = an.parse_usage(USAGE["data"])
    for patch in (
        {"currency": "EUR"},
        {"amount": "12.3.4"},
        {"amount": 1234},
        {"list_amount": None},
    ):
        row = json.loads(json.dumps(COST["data"][0]))
        row["cost"].update(patch)
        with pytest.raises(an.SourceError):
            an.cost_csv([row], usage, cfg())


def test_check_reports_each_layer_separately(monkeypatch):
    with_data = datetime(
        2026, 10, 31, 12, tzinfo=UTC
    )  # the two days before it are a Thursday and a Friday
    quiet = an.check(cfg(), Server().client(), NOW)  # nothing in the last two days of the sample
    assert quiet[-1].name == "data" and not quiet[-1].ok and "no usage" in quiet[-1].message
    steps = an.check(cfg(), Server().client(), with_data)
    assert [(s.name, s.ok) for s in steps] == [
        ("configuration", True),
        ("credential", True),
        ("access", True),
        ("data", True),
    ]
    monkeypatch.delenv(ENV)
    steps = an.check(cfg(), Server().client(), NOW)
    assert [(s.name, s.ok) for s in steps] == [("configuration", True), ("credential", False)]
    monkeypatch.setenv(ENV, FAKE_KEY)
    srv = Server()
    srv.fail = [403]
    steps = an.check(cfg(), srv.client(), NOW)
    assert steps[-1].name == "access" and not steps[-1].ok and FAKE_KEY not in steps[-1].message
    steps = an.check(cfg(), Server(refreshed=None, usage={"data": []}).client(), NOW)
    assert steps[-1].name == "data" and not steps[-1].ok


# ---- end to end against PostgreSQL, as a restricted role -------------------------------------------------

needs_db = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")
TOTAL_TOKENS = sum(r["usage"]["total_tokens"] for r in USAGE["data"])
COST_USD = sum(Decimal(r["cost"]["amount"]) for r in COST["data"]) / 100


class World:
    def __init__(self, env):
        self.env = env
        self.t, self.other = two_tenants(env)
        with app(env, self.t) as db:
            self.cid = an.create_connector(db, self.t, "anthropic-sample", SCOPE)
        self.cfg = cfg()

    def pull(self, server, now=NOW):
        with app(self.env, self.t) as db:
            return an.pull(db, self.t, self.cid, self.cfg, server.client(), now)

    def scalar(self, sql, tid=None, **kw):
        with app(self.env, tid or self.t) as db:
            return db.execute(text(sql), kw).scalar()


@pytest.fixture
def w(env):
    return World(env)


LEDGER_TOTAL = "select coalesce(sum(value), 0) from usage_aggregate_observations where provider = 'anthropic' and category = 'total'"
FOCUS_TOTAL = """select coalesce(sum(effective_cost), 0) from focus_cost_records r where service_provider_name = 'Anthropic'
                 and not exists (select 1 from focus_supersessions s where s.tenant_id = r.tenant_id and s.record_id = r.id)"""


@needs_db
def test_a_pull_stores_usage_in_the_ledger_and_cost_as_focus_rows_and_the_totals_match(w):
    out = w.pull(Server())
    # a 60-day lookback from mid-November splits October across two 31-day windows
    assert [(o.status, o.rows > 0) for o in out if o.status != "no_data"] == [
        ("imported", True)
    ] * 2
    assert Decimal(str(w.scalar(LEDGER_TOTAL))) == TOTAL_TOKENS
    assert w.scalar(FOCUS_TOTAL) == COST_USD
    assert (
        w.scalar(
            "select count(*) from usage_aggregate_observations where source_type = 'vendor_admin_api' and sku = 'unknown'"
        )
        > 0
    )
    assert w.scalar("select count(*) from ingestion_runs where status = 'succeeded'") == 2


@needs_db
def test_a_second_pull_changes_nothing(w):
    w.pull(Server())
    before = (
        w.scalar("select count(*) from focus_cost_records"),
        w.scalar("select count(*) from usage_aggregate_observations"),
    )
    out = w.pull(Server())
    assert [o.status for o in out if o.status != "no_data"] == ["already_imported"] * 2
    assert "'unchanged'" in out[-1].detail
    after = (
        w.scalar("select count(*) from focus_cost_records"),
        w.scalar("select count(*) from usage_aggregate_observations"),
    )
    assert before == after and w.scalar(FOCUS_TOTAL) == COST_USD


@needs_db
def test_revised_data_replaces_earlier_cost_keeps_history_and_revises_the_ledger(w):
    w.pull(Server())
    revised_cost = json.loads(json.dumps(COST))
    row = revised_cost["data"][0]
    row["cost"]["amount"] = (
        f"{Decimal(row['cost']['amount']) + Decimal('100.000000'):f}"  # one more dollar
    )
    revised_usage = json.loads(json.dumps(USAGE))
    revised_usage["data"][0]["usage"]["output_tokens"] += 10
    revised_usage["data"][0]["usage"]["total_tokens"] += 10
    out = w.pull(Server(usage=revised_usage, cost=revised_cost))
    assert any(o.status == "imported" and o.superseded > 0 for o in out)
    assert w.scalar(FOCUS_TOTAL) == COST_USD + Decimal(1)
    assert (
        w.scalar("select count(*) from focus_supersessions") > 0
    )  # the earlier rows are history, not deleted
    assert (
        w.scalar(
            "select max(revision) from usage_aggregate_observations where provider = 'anthropic'"
        )
        == 2
    )


@needs_db
def test_days_newer_than_data_refreshed_at_are_left_for_later(w):
    out = w.pull(Server(refreshed="2026-10-20T04:00:00Z"))
    assert any("left for later" in o.detail for o in out)
    assert (
        w.scalar("select max(charge_period_end) from focus_cost_records")
        .isoformat()
        .startswith("2026-10-20")
    )
    assert (
        w.scalar(
            "select max(window_end) from usage_aggregate_observations where provider = 'anthropic'"
        )
        .isoformat()
        .startswith("2026-10-20")
    )
    w.pull(Server())  # the rest arrives on a later run
    assert w.scalar(FOCUS_TOTAL) == COST_USD


@needs_db
def test_finality_follows_the_seven_day_revision_window_after_month_end(w):
    w.pull(Server(refreshed="2026-11-02T04:00:00Z"))
    assert (
        w.scalar("select finality from ingestion_runs where status = 'succeeded' limit 1")
        == "provisional"
    )
    with w.env.begin() as c:
        c.execute(text("delete from focus_supersessions"))
    revised = json.loads(json.dumps(COST))
    revised["data"][0]["cost"]["amount"] = "1.000000"  # different content, so it is imported again
    w.pull(Server(refreshed="2026-11-09T04:00:00Z", cost=revised))
    assert (
        w.scalar(
            "select finality from ingestion_runs where status = 'succeeded' order by started_at desc limit 1"
        )
        == "final"
    )


@needs_db
def test_the_ai_token_view_reads_anthropic_cost_with_model_direction_and_cache_action(w):
    w.pull(Server())
    with app(w.env, w.t) as db:
        rep = ai_token_report(
            db, datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)
        )
    (m,) = [m for m in rep.models if m.provider == "Anthropic"]
    assert m.model_id == "example-model-a" and m.input_tokens and m.output_tokens
    assert m.cache_hit_rate is not None and Decimal("0.5") < m.cache_hit_rate < Decimal("0.9")
    out = next(r for r in rep.rows if r.direction == "Output")
    assert abs(out.effective_cost_per_million_tokens - Decimal("13.5")) < Decimal(
        "0.01"
    )  # $15 list, 10% off
    assert rep.rows_without_direction == 0 and rep.rows_with_invalid_values == 0


@needs_db
def test_a_rejected_credential_stores_nothing_and_says_why_without_the_key(w):
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
def test_aggregate_mode_stores_no_person_and_one_tenant_never_sees_anothers_data(w):
    srv = Server()
    w.pull(srv)
    assert all("actor" not in dict(r.url.params.multi_items()).values() for r in srv.requests)
    assert (
        w.scalar(
            "select count(*) from focus_cost_records where tags::text ~ '@' or extensions::text ~ '@' or sku_price_details::text ~ '@'"
        )
        == 0
    )
    assert (
        w.scalar(
            "select count(*) from usage_aggregate_observations where account ~ '@' or model_id ~ '@'"
        )
        == 0
    )
    with app(w.env, w.other) as db:
        assert db.execute(text("select count(*) from focus_cost_records")).scalar() == 0
        assert db.execute(text("select count(*) from usage_aggregate_observations")).scalar() == 0


@needs_db
def test_an_actor_row_from_the_source_is_refused_and_nothing_is_stored(w):
    out = w.pull(Server(usage=ACTOR))
    assert out[-1].status == "failed" and "person-level" in out[-1].detail
    assert w.scalar("select count(*) from usage_aggregate_observations") == 0


@needs_db
def test_the_cli_adds_checks_and_runs_an_anthropic_connector_and_refuses_a_key_in_the_settings(
    env, tmp_path, capsys, monkeypatch
):
    t, _ = two_tenants(env)
    scope = tmp_path / "scope.json"
    scope.write_text(json.dumps(SCOPE))
    assert admin.main(["connector-add", "anthropic", str(t), "cli-anthropic", str(scope)]) == 0
    assert len(capsys.readouterr().out.strip()) == 36
    scope.write_text(json.dumps({**SCOPE, "api_key": FAKE_KEY}))
    assert admin.main(["connector-add", "anthropic", str(t), "cli-bad", str(scope)]) == 1
    err = capsys.readouterr().err
    assert "refused" in err and FAKE_KEY not in err
    scope.write_text(json.dumps({**SCOPE, "mode": "per_user"}))
    assert admin.main(["connector-add", "anthropic", str(t), "cli-peruser", str(scope)]) == 1
    assert "not built yet" in capsys.readouterr().err
    with env.connect() as c:  # the reference is in the column, never the key
        stored = c.execute(
            text("select credential_ref, scope::text from connectors where name = 'cli-anthropic'")
        ).one()
    assert stored[0] == f"env:{ENV}" and FAKE_KEY not in stored[1] and "credential" not in stored[1]

    srv = Server()
    monkeypatch.setattr(an, "build_client", lambda c: srv.client())
    monkeypatch.setattr(
        an,
        "windows",
        lambda c, now=None: [
            (datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC))
        ],
    )
    assert admin.main(["connector-run", str(t), "cli-anthropic", "--dry-run"]) == 0
    assert "would read 2026-10-01 to 2026-11-01" in capsys.readouterr().out and srv.requests == []
    assert admin.main(["connector-run", str(t), "cli-anthropic"]) == 0
    assert "imported" in capsys.readouterr().out
    assert admin.main(["connector-status", str(t), "cli-anthropic"]) == 0
    assert '"rows"' in capsys.readouterr().out
    monkeypatch.delenv(ENV)
    assert admin.main(["connector-check", str(t), "cli-anthropic"]) == 1
    assert "FAIL credential" in capsys.readouterr().out
