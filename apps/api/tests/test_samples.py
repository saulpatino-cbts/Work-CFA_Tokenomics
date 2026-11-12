"""The synthetic sample sets: deterministic, clearly fictional, internally consistent, and importable end to
end through the cost-export connectors. Nothing here is real data."""

import csv
import gzip
import io
import json
import os
import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from conftest import app, two_tenants
from sqlalchemy import text
from test_connectors_pull import Store

from cfa_tokenomics import store as econ_store
from cfa_tokenomics.alloc import runner as alloc
from cfa_tokenomics.connectors import costexport as cx
from cfa_tokenomics.focus.ai import ai_token_report
from cfa_tokenomics.focus.parse import parse_focus_csv
from cfa_tokenomics.samples import cast
from cfa_tokenomics.samples.__main__ import main as samples_main
from cfa_tokenomics.samples.generate import build_all, cost_rows

URL = os.environ.get("CFA_TEST_DATABASE_URL")
NOW = datetime(2026, 11, 5, tzinfo=UTC)
START, END = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)
SAMPLES = build_all()


def rows_of(prefix: str) -> list[dict]:
    out = []
    for path, data in SAMPLES.items():
        if path.startswith(prefix) and path.endswith(".csv.gz"):
            out += list(csv.DictReader(io.StringIO(gzip.decompress(data).decode())))
    return out


# ---- the files themselves (no database) --------------------------------------------------------------


def test_the_same_arguments_give_byte_identical_files_and_a_different_seed_differs():
    assert build_all() == SAMPLES
    assert build_all(seed=8) != SAMPLES
    assert build_all(month="2026-09") != SAMPLES


def test_everything_is_visibly_fictional():
    text_blob = "\n".join(
        (gzip.decompress(d).decode() if p.endswith(".gz") else d.decode())
        for p, d in SAMPLES.items()
    )
    assert set(re.findall(r"[\w.+-]+@[\w.-]+", text_blob)) <= {u.email for u in cast.USERS}
    assert all(u.email.endswith("@example.test") for u in cast.USERS)
    for pattern in (
        r"AKIA[0-9A-Z]{16}",
        r"sk-(ant|admin|proj)",
        r"eyJ[A-Za-z0-9_-]{20,}",
        r"-----BEGIN",
    ):
        assert not re.search(pattern, text_blob), pattern
    for r in rows_of("aws/") + rows_of("azure/"):
        assert r["x_SyntheticSample"] == "true"
        assert r["BillingAccountId"] in (cast.AWS_ACCOUNT, cast.AZURE_SUBSCRIPTION)


def test_cost_rows_follow_the_pricing_and_stay_exact():
    for r in rows_of("aws/"):
        for col in ("BilledCost", "EffectiveCost", "ListCost", "ContractedCost"):
            assert (
                len(Decimal(r[col]).as_tuple().digits) < 20
                and -Decimal(r[col]).as_tuple().exponent <= 6
            )
        if (
            r["ChargeCategory"] == "Usage"
            and not r["ChargeClass"]
            and r["ConsumedUnit"] == "Tokens"
        ):
            assert Decimal(r["ContractedCost"]) <= Decimal(r["ListCost"])
    aws, az = cost_rows("2026-10", 7, False)
    assert {r["ChargeCategory"] for r in aws} == {"Usage", "Tax", "Credit", "Purchase"}
    assert {r["ChargeCategory"] for r in az} == {"Usage", "Tax", "Credit"}
    assert any(r.get("ChargeClass") == "Correction" for r in aws + az)
    untagged = [r for r in aws if r["ChargeCategory"] == "Usage" and "Tags" not in r]
    assert untagged  # shared lines with no application tag, so some cost stays unallocated


def test_the_openai_sample_is_consistent_between_per_user_and_workspace_rows():
    per = json.loads(SAMPLES["openai/daily_usage_per_user.json"])["data"]
    ws = json.loads(SAMPLES["openai/daily_usage_workspace.json"])["data"]
    assert per and ws and all(r["object"] == "workspace.usage.result" for r in per + ws)
    allowed_clients = {"CODEX_CLI", "CODEX_WEB"}
    for r in per:
        assert r["user_id"] in {u.user_id for u in cast.USERS}
        assert r["actor"]["email"] == next(u.email for u in cast.USERS if u.user_id == r["user_id"])
        assert r["totals"]["chats"] == sum(c["chats"] for c in r["clients"])
        assert r["totals"]["messages"] == sum(c["messages"] for c in r["clients"])
        assert {c["client_id"] for c in r["clients"]} <= allowed_clients
        t = r["totals"]
        assert (t["credits"] is None) or (
            t.get("cost_usd") is None
        )  # credit-priced or USD-priced, as documented
    by_day: dict[int, dict] = {}
    for r in per:
        d = by_day.setdefault(
            r["start_time"], {"chats": 0, "messages": 0, "credits": Decimal(0), "usd": Decimal(0)}
        )
        d["chats"] += r["totals"]["chats"]
        d["messages"] += r["totals"]["messages"]
        d["credits"] += Decimal(str(r["totals"]["credits"] or 0))
        d["usd"] += Decimal(str(r["totals"].get("cost_usd") or 0))
    assert set(by_day) == {r["start_time"] for r in ws}
    for r in ws:
        d = by_day[r["start_time"]]
        assert r["user_id"] is None and r["actor"] is None
        assert (r["totals"]["chats"], r["totals"]["messages"]) == (d["chats"], d["messages"])
        assert Decimal(str(r["totals"]["credits"] or 0)) == d["credits"]
        assert Decimal(str(r["totals"]["cost_usd"] or 0)) == d["usd"]


def test_the_anthropic_sample_follows_the_documented_shape():
    cost = json.loads(SAMPLES["anthropic/analytics_cost_by_model.json"])
    use = json.loads(SAMPLES["anthropic/analytics_usage_by_model.json"])
    actor = json.loads(SAMPLES["anthropic/analytics_usage_by_actor.json"])
    for doc in (cost, use, actor):
        assert (
            set(doc) == {"data", "has_more", "next_page", "data_refreshed_at"}
            and doc["has_more"] is False
        )
    keys = set(use["data"][0]["group"])
    assert len(keys) == 19 and keys == set(actor["data"][0]["group"])
    for row in cost["data"]:
        c = row["cost"]
        assert re.fullmatch(r"-?\d+\.\d{6}", c["amount"]) and re.fullmatch(
            r"-?\d+\.\d{6}", c["list_amount"]
        )
        assert (
            Decimal(c["amount"]) <= Decimal(c["list_amount"])
            and c["currency"] == "USD"
            and c["requests"] is None
        )
        assert row["group"]["cost_type"] == "tokens" and "token_type" in row["group"]
    for row in use["data"] + actor["data"]:
        u = row["usage"]
        assert u["total_tokens"] == u["uncached_input_tokens"] + u["cache_read_input_tokens"] + u[
            "output_tokens"
        ] + sum(u["cache_creation"].values())
    dev = {x.user_id for x in cast.users_of("platform-eng")}
    assert {
        r["group"]["actor"]["user_id"] for r in actor["data"]
    } <= dev  # the same people as the Codex sample


def test_the_identity_variant_adds_only_the_draft_identity_columns_which_the_importer_drops():
    plain = build_all(identity=False)
    ident = build_all(identity=True)
    part = "aws/cur/focus/data/BILLING_PERIOD=2026-10/export-00001.csv.gz"
    assert "PrincipalId" not in gzip.decompress(plain[part]).decode().splitlines()[0]
    head = gzip.decompress(ident[part]).decode().splitlines()[0]
    assert "PrincipalId" in head and "CredentialId" in head
    parsed = parse_focus_csv(gzip.decompress(ident[part]), "1.2", 10_000_000)
    assert set(parsed.dropped_identity_columns) == {"PrincipalId", "CredentialId"}
    assert not parsed.rejects
    assert plain.keys() == ident.keys()
    users = {f"principal/{u.user_id}" for u in cast.USERS} | {""}
    assert {
        r["PrincipalId"] for r in csv.DictReader(io.StringIO(gzip.decompress(ident[part]).decode()))
    } <= users


def test_the_command_writes_the_tree_and_refuses_bad_input(tmp_path, capsys):
    assert samples_main([str(tmp_path), "--month", "2026-10"]) == 0
    assert (tmp_path / "README.txt").read_text().startswith("SYNTHETIC SAMPLE DATA")
    assert (tmp_path / "aws/cur/focus/data/BILLING_PERIOD=2026-10/export-00001.csv.gz").exists()
    assert samples_main([str(tmp_path), "--month", "2026-13"]) == 2
    assert samples_main([]) == 2
    capsys.readouterr()


# ---- through the connectors, the AI token view and allocation (database) ----------------------------------


pytestmark_db = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")


def loaded_store(prefix: str) -> Store:
    st = Store()
    for path, data in SAMPLES.items():
        if path.startswith(prefix) and not path.endswith(("README.txt",)):
            st.put(path[len(prefix) :], data, modified=datetime(2026, 11, 1, tzinfo=UTC))
    return st


AWS_SCOPE = {"bucket": "example-exports", "prefix": "cur/focus", "lookback_periods": 24}
AZURE_SCOPE = {
    "account_url": "https://example.blob.core.windows.net",
    "container": "exports",
    "prefix": "ea/focus",
    "lookback_periods": 24,
}


@pytestmark_db
def test_both_trees_import_through_the_connectors_and_the_totals_match_the_files(env):
    t, _ = two_tenants(env)
    for provider, scope, prefix in (("aws", AWS_SCOPE, "aws/"), ("azure", AZURE_SCOPE, "azure/")):
        cfg = cx.parse_scope(provider, scope)
        with app(env, t) as db:
            cid = cx.create_connector(db, t, provider, f"{provider}-sample", scope)
            out = cx.pull(db, t, cid, cfg, loaded_store(prefix), NOW)
        assert [o.status for o in out] == ["imported"], out
        want = rows_of(prefix)
        assert out[0].rows == len(want)
        with app(env, t) as db:
            got = db.execute(
                text(
                    "select coalesce(sum(effective_cost), 0), count(*) from focus_cost_records r join ingestion_runs i on i.id = r.ingestion_run_id join connectors c on c.id = i.connector_id where c.name = :n"
                ),
                {"n": f"{provider}-sample"},
            ).one()
        assert got[1] == len(want) and got[0] == sum(Decimal(r["EffectiveCost"]) for r in want)


@pytestmark_db
def test_the_ai_token_view_reads_the_samples_and_matches_the_files(env):
    t, _ = two_tenants(env)
    for provider, scope, prefix in (("aws", AWS_SCOPE, "aws/"), ("azure", AZURE_SCOPE, "azure/")):
        with app(env, t) as db:
            cid = cx.create_connector(db, t, provider, f"{provider}-sample", scope)
            cx.pull(db, t, cid, cx.parse_scope(provider, scope), loaded_store(prefix), NOW)
    with app(env, t) as db:
        rep = ai_token_report(db, START, END)
    by = {(m.provider, m.model_id): m for m in rep.models}
    assert set(by) == {("Amazon Web Services", "example-model-a"), ("Microsoft", "example-model-b")}
    for (prov, _model_id), m in by.items():
        prefix = "aws/" if prov.startswith("Amazon") else "azure/"
        rows = [
            r for r in rows_of(prefix) if r["ConsumedUnit"] == "Tokens" and not r["ChargeClass"]
        ]
        want_in = sum(
            Decimal(r["ConsumedQuantity"])
            for r in rows
            if '"TokenDirection":"Input"' in r["SkuPriceDetails"]
        )
        want_out = sum(
            Decimal(r["ConsumedQuantity"])
            for r in rows
            if '"TokenDirection":"Output"' in r["SkuPriceDetails"]
        )
        assert (m.input_tokens, m.output_tokens) == (want_in, want_out)
        assert m.cache_hit_rate is not None and Decimal("0.30") < m.cache_hit_rate < Decimal(
            "0.34"
        )  # read is half of uncached
        assert m.correction_effective_cost < 0  # the correction row is its own line, never hidden
    assert rep.rows_without_direction == 0 and rep.rows_with_invalid_values == 0


@pytestmark_db
def test_tag_allocation_covers_the_tagged_cost_and_reports_the_shared_remainder(env):
    t, _ = two_tenants(env)
    scope = AWS_SCOPE
    with app(env, t) as db:
        cid = cx.create_connector(db, t, "aws", "aws-sample", scope)
        cx.pull(db, t, cid, cx.parse_scope("aws", scope), loaded_store("aws/"), NOW)
        for a in cast.APPS:
            econ_store.create_application(db, t, a.key, "usd")
        alloc.create_rule(
            db, t, "by-app-tag", "Allocate by app tag", 10, "tag", {"tag_key": "app"}, "tester"
        )
        res = alloc.run_allocation(db, t, START, END, "tester", now=NOW)
        assert res.status == "succeeded", res
        s = next(x for x in alloc.allocation_summary(db) if x.currency == "USD")
    assert s.allocated_effective > 0 and s.unallocated_effective > 0
    assert (
        s.allocated_effective + s.unallocated_effective + s.not_yet_allocated_effective
        == s.total_effective
    )
    assert "tag_missing" in s.unallocated_by_reason  # the shared, untagged lines carry a reason
    assert Decimal("0.5") < s.coverage < Decimal(1)
