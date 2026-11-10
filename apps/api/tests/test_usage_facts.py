"""Usage facts: the normalized, exact-decimal projection of the ledger. All data is SYNTHETIC."""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from conftest import app, two_tenants
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from cfa_tokenomics import admin
from cfa_tokenomics.usage import ledger
from cfa_tokenomics.usage.facts import project_usage
from cfa_tokenomics.usage.models import AggregateObservation, Quality, RequestObservation

URL = os.environ.get("CFA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")
T = datetime(2026, 1, 1, tzinfo=UTC)


def req(rid="r1", **kw):
    base = dict(provider="bedrock", account="a", model_id="m", attempt=1, occurred_at=T)
    return RequestObservation(request_id=rid, **{**base, **kw})


def agg(value, category="input", **kw):
    return AggregateObservation(
        **{
            **dict(provider="bedrock", account="a", model_id="m", statistic="Sum",
                   window_start=T, window_end=T + timedelta(minutes=5)),
            **kw, "category": category, "value": value,
        }
    )  # fmt: skip


def facts(db, **where):
    cond = " and ".join(f"{k} = :{k}" for k in where) or "true"
    rows = db.execute(
        text(
            "select grain, measure, quantity, basis, quality, revision, source_table, statistic, unit "
            f"from usage_facts where {cond} order by grain, measure, source_id"
        ),
        where,
    ).all()
    return rows


def test_only_known_categories_become_facts_and_unknown_is_not_zero(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        ledger.record_request(db, req(input=7, output=3))  # the other categories are unknown
        res = project_usage(db)
        assert (res.request_rows, res.request_facts) == (1, 2)
        got = {(r.measure, r.quantity, r.unit, r.grain, r.statistic) for r in facts(db)}
        assert got == {
            ("input", 7, "tokens", "request", None),
            ("output", 3, "tokens", "request", None),
        }


def test_zero_is_kept_when_it_was_reported(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        ledger.record_request(db, req(input=0))
        project_usage(db)
        assert [(r.measure, r.quantity) for r in facts(db)] == [("input", 0)]


def test_quality_maps_to_basis_without_ever_upgrading_to_observed(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        for i, q in enumerate(Quality):
            ledger.record_request(db, req(f"r{i}", input=1, quality=q))
        project_usage(db)
        basis = {r.quality: r.basis for r in facts(db)}
    assert basis == {
        "reported": "observed",
        "partial": "observed",
        "estimated": "estimated",
        "unknown": "estimated",
    }


def test_aggregates_are_exact_and_keep_their_window_and_statistic(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        ledger.upsert_aggregate(db, agg(10.0))
        ledger.upsert_aggregate(db, agg(0.1, "output"))
        ledger.upsert_aggregate(db, agg(123456789012345678.0, "cache_read"))
        project_usage(db)
        got = {r.measure: r.quantity for r in facts(db, grain="window")}
        assert got["input"] == Decimal(10) and got["output"] == Decimal(
            "0.1"
        )  # not 0.1000000000000000055
        assert got["cache_read"] == Decimal("123456789012345680")  # the double's own shortest form
        row = db.execute(
            text(
                "select period_start, period_end, statistic from usage_facts where measure = 'input'"
            )
        ).one()
        assert (row.period_start, row.period_end, row.statistic) == (
            T,
            T + timedelta(minutes=5),
            "Sum",
        )


def test_projection_is_idempotent_and_revisions_update_only_what_changed(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        ledger.record_request(db, req(input=5))
        ledger.upsert_aggregate(db, agg(10.0))
        ledger.upsert_aggregate(db, agg(1.0, "output"))
        first = project_usage(db)
        assert (first.request_facts, first.aggregate_inserted, first.aggregate_unchanged) == (
            1,
            2,
            0,
        )
        again = project_usage(db)
        assert (
            again.request_facts,
            again.aggregate_inserted,
            again.aggregate_revised,
            again.aggregate_unchanged,
        ) == (0, 0, 0, 2)
        assert ledger.upsert_aggregate(db, agg(12.0)) == "revised"
        third = project_usage(db)
        assert (third.aggregate_revised, third.aggregate_unchanged) == (1, 1)
        got = {r.measure: (r.quantity, r.revision) for r in facts(db, grain="window")}
        assert got == {"input": (12, 2), "output": (1, 1)}
        assert (
            db.execute(text("select count(*) from usage_facts")).scalar() == 3
        )  # revised in place, no duplicate


def test_sources_are_kept_apart_never_added(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        ledger.upsert_aggregate(db, agg(10.0, source_type="cloud_telemetry"))
        ledger.upsert_aggregate(db, agg(12.0, source_type="vendor_admin_api"))
        ledger.record_request(db, req(input=9))
        project_usage(db)
        rows = db.execute(
            text("select source_type, quantity from usage_facts order by source_type, quantity")
        ).all()
    assert [(r.source_type, r.quantity) for r in rows] == [
        ("app_routed", 9),
        ("cloud_telemetry", 10),
        ("vendor_admin_api", 12),
    ]


def test_non_finite_provider_values_are_skipped_and_counted(env):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        ledger.upsert_aggregate(db, agg(1.0))
        db.execute(
            text(
                "update usage_aggregate_observations set value = 'NaN'::float8 where category = 'input'"
            )
        )
        ledger.upsert_aggregate(db, agg(5.0, "output"))
        db.commit()
        res = project_usage(db)
        assert (res.aggregate_inserted, res.skipped_nonfinite) == (1, 1)
        assert [r.measure for r in facts(db)] == ["output"]


def test_each_tenant_projects_and_sees_only_its_own_ledger(env):
    a, b = two_tenants(env)
    with app(env, a) as db:
        ledger.record_request(db, req(input=1))
    with app(env, b) as db:
        ledger.record_request(db, req(input=2))
        res = project_usage(db)
        assert res.request_facts == 1
        assert [r.quantity for r in facts(db)] == [2]
    with app(env, a) as db:
        assert (
            db.execute(text("select count(*) from usage_facts")).scalar() == 0
        )  # not projected yet
        project_usage(db)
        assert [r.quantity for r in facts(db)] == [1]


def test_a_fact_cannot_be_written_for_another_tenant_or_break_its_own_shape(env):
    a, b = two_tenants(env)
    row = (
        "insert into usage_facts (id, tenant_id, grain, provider, account, model_id, sku, source_type, "
        "measure, statistic, quantity, period_start, period_end, basis, quality, normalization_version, "
        "source_table, source_id) values (gen_random_uuid(), :t, :g, 'p','a','m','unknown','app_routed',"
        ":m, :s, :q, now(), now(), :b, 'reported','1','usage_request_observations', 1)"
    )
    ok = dict(t=a, g="request", m="input", s=None, q=1, b="observed")
    with app(env, a) as db:
        db.execute(text(row), ok)
        db.commit()
    for bad in (
        {**ok, "t": b},
        {**ok, "q": -1},
        {**ok, "b": "guess"},
        {**ok, "m": "bogus"},
        {**ok, "s": "Sum"},
        {**ok, "g": "window"},
    ):
        with app(env, a) as db, pytest.raises((DBAPIError, IntegrityError)):
            db.execute(text(row), bad)
            db.commit()


def test_the_project_usage_command_reports_what_it_did(env, capsys):
    a, _ = two_tenants(env)
    with app(env, a) as db:
        ledger.record_request(db, req(input=1))
        ledger.upsert_aggregate(db, agg(2.0))
    assert admin.main(["project-usage", str(a)]) == 0
    out = capsys.readouterr().out
    assert "requests: 1 facts from 1 rows" in out and "aggregates: 1 new" in out
