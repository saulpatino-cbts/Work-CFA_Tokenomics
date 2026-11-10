"""Allocation runs against real PostgreSQL, as a restricted role. All data is SYNTHETIC."""

import csv
import io
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from conftest import _as, app, two_tenants
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from cfa_tokenomics import admin, migrate, store
from cfa_tokenomics.alloc import runner as R
from cfa_tokenomics.alloc import tables as T
from cfa_tokenomics.focus import importer as imp

URL = os.environ.get("CFA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")

COLS = [
    "BilledCost", "EffectiveCost", "ListCost", "ContractedCost", "ChargeCategory", "ChargePeriodStart",
    "ChargePeriodEnd", "BillingCurrency", "BillingAccountId", "SubAccountId", "ServiceName", "Tags",
    "AllocatedMethodId",
]  # fmt: skip
JAN1, FEB1 = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)
NOW = datetime(2026, 3, 1, tzinfo=UTC)


def row(amount, day, *, tags=None, service="Bedrock", cur="USD", cat="Usage", eff=None, split=""):
    eff = amount if eff is None else eff
    return [
        amount, eff, amount, amount, cat, f"2026-01-{day:02d}T00:00:00Z", (datetime(2026, 1, day, tzinfo=UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        cur, "ba1", "sub1", service, json.dumps(tags) if tags is not None else "", split,
    ]  # fmt: skip


def file(*rows):
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(COLS)
    w.writerows(rows)
    return out.getvalue().encode()


class World:
    def __init__(self, env):
        self.env = env
        self.t, self.other = two_tenants(env)
        with app(env, self.t) as db:
            self.cid = imp.get_or_create_manual_connector(db, self.t)
            self.apps = {
                n: store.create_application(db, self.t, n, "usd").id
                for n in ("claims", "search", "shared-a", "shared-b")
            }

    def session(self):
        return app(self.env, self.t)

    def load(self, db, name, *rows):
        res = imp.import_focus_file(
            db, self.t, self.cid, name, file(*rows), declared_version="1.2", now=NOW
        )
        assert res.status == "succeeded", res
        return res

    def rule(self, db, key, method, params, **kw):
        kw.setdefault("priority", 10)
        return R.create_rule(db, self.t, key, key, method=method, params=params, author="ann", **kw)

    def run(self, db):
        return R.run_allocation(db, self.t, JAN1, FEB1, "ann", now=NOW)


@pytest.fixture
def w(env):
    return World(env)


def summary(db, currency="USD"):
    return next(s for s in R.allocation_summary(db) if s.currency == currency)


# ---- rules -----------------------------------------------------------------------------------------


def test_rules_are_versioned_validated_and_must_name_real_applications(w):
    a = str(w.apps["claims"])
    with w.session() as db:
        assert w.rule(db, "r1", "direct", {"application_id": a}) == 1
        assert w.rule(db, "r1", "direct", {"application_id": a}, priority=5) == 2
        assert [(r.key, r.version, r.priority) for r in R.current_rules(db)] == [("r1", 2, 5)]
        w.rule(
            db, "r1", "direct", {"application_id": a}, enabled=False
        )  # disabling is a new version
        assert R.current_rules(db) == []
        assert (
            db.scalar(select(func.count()).select_from(T.allocation_rules)) == 3
        )  # nothing was edited
        with pytest.raises(ValueError):
            w.rule(db, "bad", "fixed_percent", {"targets": []})
        with pytest.raises(R.AllocationError, match="does not exist"):
            w.rule(db, "ghost", "direct", {"application_id": str(uuid.uuid4())})
        with pytest.raises(R.AllocationError, match="workload"):
            w.rule(db, "wl", "direct", {"application_id": a, "workload_id": str(uuid.uuid4())})


def test_a_rule_cannot_name_another_tenants_application(w, env):
    with app(env, w.other) as db:
        foreign = store.create_application(db, w.other, "theirs", "usd").id
    with w.session() as db, pytest.raises(R.AllocationError, match="does not exist"):
        w.rule(db, "steal", "direct", {"application_id": str(foreign)})


# ---- runs ------------------------------------------------------------------------------------------


def test_a_run_allocates_by_tag_shares_by_even_split_and_reports_the_rest(w):
    with w.session() as db:
        w.load(db, "jan.csv", row(100, 1, tags={"app": "claims"}), row(40, 2, tags={"app": "search"}),
               row("0.01", 3, service="Shared"), row(7, 4, tags={"app": "nobody"}), row(5, 5))  # fmt: skip
        w.rule(db, "tag", "tag", {"tag_key": "app"}, priority=1)
        w.rule(db, "shared", "even", {"application_ids": [str(w.apps["shared-a"]), str(w.apps["shared-b"])]},
               priority=5, conditions=[{"field": "service_name", "op": "eq", "value": "Shared"}])  # fmt: skip
        res = w.run(db)
        assert (res.status, res.lines, res.slices) == ("succeeded", 5, 6)
        by_app = {r["application_id"]: r["effective"] for r in R.allocated_cost_by_application(db)}
        assert by_app[w.apps["claims"]] == 100 and by_app[w.apps["search"]] == 40
        assert by_app[w.apps["shared-a"]] + by_app[w.apps["shared-b"]] == Decimal("0.01")  # exact
        s = summary(db)
        assert s.total_effective == Decimal("152.01")
        assert s.allocated_effective == Decimal("140.01") and s.unallocated_effective == 12
        assert s.not_yet_allocated_effective == 0
        assert s.unallocated_by_reason == {
            "tag_unmapped": 7,
            "tag_missing": 5,
        }  # the informative reason, not "no_rule"
        assert s.by_method == {"tag": 140, "even": Decimal("0.01")}
        assert s.coverage == Decimal("140.01") / Decimal("152.01")
        assert R.verify_allocation(db) == []  # every line adds up in every measure


def test_every_measure_of_every_line_adds_up_exactly(w):
    awkward = [
        row("0.01", 1),
        row("0.000000000000000001", 2),
        row("-37.5", 3),
        row("99999999999999999999.999999999999999999", 4),
    ]
    with w.session() as db:
        w.load(db, "x.csv", *awkward)
        w.rule(
            db,
            "even3",
            "even",
            {"application_ids": [str(w.apps[n]) for n in ("claims", "search", "shared-a")]},
        )
        w.run(db)
        assert R.verify_allocation(db) == []
        assert db.scalar(select(func.count()).select_from(T.allocated_costs)) == 12


def test_rerunning_with_nothing_changed_adds_nothing_and_a_change_makes_a_new_run(w):
    a = str(w.apps["claims"])
    with w.session() as db:
        w.load(db, "jan.csv", row(10, 1), row(20, 2))
        w.rule(db, "all", "direct", {"application_id": a})
        first = w.run(db)
        again = w.run(db)
        assert again.status == "unchanged" and again.run_id == first.run_id
        assert db.scalar(select(func.count()).select_from(T.allocated_costs)) == 2
        w.rule(
            db, "all", "direct", {"application_id": str(w.apps["search"])}
        )  # rule v2 moves the cost
        changed = w.run(db)
        assert changed.status == "succeeded" and changed.run_id != first.run_id
        by_app = {r["application_id"]: r["effective"] for r in R.allocated_cost_by_application(db)}
        assert by_app == {w.apps["search"]: 30}  # the latest run is current
        assert (
            db.scalar(select(func.count()).select_from(T.allocated_costs)) == 4
        )  # history is kept
        assert (
            db.scalar(
                select(func.count())
                .select_from(T.allocation_runs)
                .where(T.allocation_runs.c.status == "succeeded")
            )
            == 2
        )


def test_proportional_allocation_uses_drivers_and_a_new_driver_version_changes_the_result(w):
    a, b = w.apps["claims"], w.apps["search"]
    with w.session() as db:
        w.load(db, "jan.csv", row(100, 1))
        w.rule(db, "tokens", "proportional", {"application_ids": [str(a), str(b)]})
        assert w.run(db).status == "succeeded"
        s = summary(db)
        assert s.unallocated_by_reason == {"driver_missing": 100}  # no guessing without drivers
        for app_id, v in ((a, 3), (b, 1)):
            R.add_driver(
                db, w.t, "tokens", app_id, JAN1, FEB1, Decimal(v), "observed", "usage export", "ann"
            )
        w.run(db)
        by_app = {r["application_id"]: r["effective"] for r in R.allocated_cost_by_application(db)}
        assert by_app == {a: 75, b: 25}
        assert (
            R.add_driver(db, w.t, "tokens", b, JAN1, FEB1, Decimal(3), "assumed", "estimate", "ann")
            == 2
        )
        w.run(db)
        by_app = {r["application_id"]: r["effective"] for r in R.allocated_cost_by_application(db)}
        assert by_app == {a: 50, b: 50}


def test_a_revised_import_leaves_the_new_lines_not_yet_allocated_until_the_next_run(w):
    with w.session() as db:
        w.load(db, "v1.csv", row(10, 1), row(20, 2))
        w.rule(db, "all", "direct", {"application_id": str(w.apps["claims"])})
        w.run(db)
        assert summary(db).coverage == 1
        w.load(db, "v2.csv", row(11, 1), row(21, 2))  # supersedes v1
        s = summary(db)
        assert (s.total_effective, s.allocated_effective, s.not_yet_allocated_effective) == (
            32,
            0,
            32,
        )
        assert (
            s.coverage == 0
        )  # superseded lines no longer count, and new ones are visibly unallocated
        w.run(db)
        s = summary(db)
        assert (s.allocated_effective, s.not_yet_allocated_effective, s.coverage) == (32, 0, 1)
        assert R.verify_allocation(db) == []


def test_currencies_are_reported_separately_and_credits_allocate(w):
    with w.session() as db:
        w.load(db, "x.csv", row(100, 1), row(50, 2, cur="EUR"), row(-30, 3, cat="Credit"))
        w.rule(db, "all", "direct", {"application_id": str(w.apps["claims"])})
        w.run(db)
        usd, eur = summary(db, "USD"), summary(db, "EUR")
        assert (usd.total_effective, eur.total_effective) == (70, 50)
        assert {r["currency"]: r["effective"] for r in R.allocated_cost_by_application(db)} == {
            "USD": 70,
            "EUR": 50,
        }
        assert R.verify_allocation(db) == []


def test_window_is_half_open_on_charge_period_start(w):
    with w.session() as db:
        w.load(db, "x.csv", row(10, 1), row(20, 31))
        w.rule(db, "all", "direct", {"application_id": str(w.apps["claims"])})
        assert (
            R.run_allocation(db, w.t, JAN1, datetime(2026, 1, 31, tzinfo=UTC), "ann", now=NOW).lines
            == 1
        )
        assert R.run_allocation(db, w.t, JAN1, FEB1, "ann", now=NOW).lines == 2


def test_provider_split_rows_are_counted_so_they_are_not_summed_blindly(w):
    with w.session() as db:
        w.load(db, "x.csv", row(100, 1), row(25, 1, split="split-v1"), row(25, 1, split="split-v1"))
        w.rule(db, "all", "direct", {"application_id": str(w.apps["claims"])})
        w.run(db)
        assert summary(db).provider_split_lines == 2


def test_a_failure_part_way_leaves_no_slices_and_earlier_results_intact(w, monkeypatch):
    with w.session() as db:
        w.load(db, "jan.csv", row(10, 1), row(20, 2))
        w.rule(db, "all", "direct", {"application_id": str(w.apps["claims"])})
        w.run(db)
        w.rule(db, "all", "direct", {"application_id": str(w.apps["search"])})
        real, calls = R.allocate_line, {"n": 0}

        def flaky(ln, rules, ctx):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("simulated crash")
            return real(ln, rules, ctx)

        monkeypatch.setattr(R, "allocate_line", flaky)
        res = w.run(db)
        assert res.status == "failed" and res.error == "allocation failed: RuntimeError"
        monkeypatch.setattr(R, "allocate_line", real)
        by_app = {r["application_id"]: r["effective"] for r in R.allocated_cost_by_application(db)}
        assert by_app == {w.apps["claims"]: 30}  # the earlier successful run is still current
        assert db.scalar(select(func.count()).select_from(T.allocated_costs)) == 2


# ---- isolation and protection ----------------------------------------------------------------------


def test_tenants_cannot_see_each_others_allocations(w, env):
    with w.session() as db:
        w.load(db, "jan.csv", row(10, 1))
        w.rule(db, "all", "direct", {"application_id": str(w.apps["claims"])})
        w.run(db)
    with app(env, w.other) as db:
        assert R.allocation_summary(db) == [] and R.allocated_cost_by_application(db) == []
        assert R.current_rules(db) == []
        assert db.scalar(select(func.count()).select_from(T.allocated_costs)) == 0


def test_allocation_history_cannot_be_edited_by_the_runtime_role(w):
    with w.session() as db:
        w.load(db, "jan.csv", row(10, 1))
        w.rule(db, "all", "direct", {"application_id": str(w.apps["claims"])})
        w.run(db)
    for stmt in ("update allocated_costs set effective_cost = 0", "delete from allocated_costs",
                 "update allocation_rules set priority = 0", "delete from allocation_drivers"):  # fmt: skip
        with w.session() as db, pytest.raises(DBAPIError, match="permission denied"):
            db.execute(text(stmt))


def test_database_constraints_back_up_the_invariants(w, env):
    with w.session() as db:
        w.load(db, "jan.csv", row(10, 1))
        w.rule(db, "all", "direct", {"application_id": str(w.apps["claims"])})
        w.run(db)
        cost_id = db.execute(text("select id from focus_cost_records")).scalar()
        run_id = db.execute(text("select id from allocation_runs")).scalar()

    def slice_sql(app_id, method, share="1"):
        return text(
            "insert into allocated_costs (id, tenant_id, allocation_run_id, focus_cost_id, application_id, method,"
            " share, billed_cost, effective_cost, list_cost, contracted_cost, billing_currency)"
            f" values (gen_random_uuid(), :t, :r, :c, {app_id}, '{method}', {share}, 1, 1, 1, 1, 'USD')"
        )

    p = {"t": w.t, "r": run_id, "c": cost_id}
    for sql, name in (
        (slice_sql("null", "direct"), "ck_alloc_unallocated"),
        (slice_sql(f"'{w.apps['claims']}'", "unallocated"), "ck_alloc_unallocated"),
        (slice_sql(f"'{w.apps['claims']}'", "direct", "1.5"), "ck_alloc_share"),
        (slice_sql(f"'{w.apps['claims']}'", "magic"), "ck_alloc_method"),
    ):
        with Session(env) as admin_db, pytest.raises(IntegrityError, match=name):
            admin_db.execute(sql, p)
            admin_db.commit()
    with (
        Session(env) as admin_db,
        pytest.raises(IntegrityError, match="fk_alloc_app"),
    ):  # foreign tenant's app
        with app(env, w.other) as other:
            foreign = store.create_application(other, w.other, "theirs", "usd").id
        admin_db.execute(slice_sql(f"'{foreign}'", "direct"), p)
        admin_db.commit()
    with Session(env) as admin_db, pytest.raises(IntegrityError, match="ck_driver_nonneg"):
        admin_db.execute(
            text("insert into allocation_drivers (id, tenant_id, rule_key, application_id, period_start, period_end, value,"
                 " basis, source, version, author) values (gen_random_uuid(), :t, 'k', :a, now(), now() + interval '1 day',"
                 " -1, 'observed', 's', 1, 'x')"),
            {"t": w.t, "a": w.apps["claims"]},
        )  # fmt: skip
        admin_db.commit()


def test_downgrade_removes_allocation_and_the_split_columns_and_upgrade_restores_them(env):
    migrate.main(["downgrade", "0006"])
    with env.connect() as c:
        tables = {
            r[0]
            for r in c.execute(text("select tablename from pg_tables where schemaname='public'"))
        }
        cols = {
            r[0]
            for r in c.execute(
                text(
                    "select column_name from information_schema.columns where table_name='focus_cost_records'"
                )
            )
        }
    assert "allocated_costs" not in tables and "focus_cost_records" in tables
    assert "allocated_method_id" not in cols
    migrate.main(["upgrade"])


def test_cli_allocate(env, tmp_path, capsys):
    t, _ = two_tenants(env)
    with app(env, t) as db:
        apps_id = store.create_application(db, t, "claims", "usd").id
        cid = imp.get_or_create_manual_connector(db, t)
        imp.import_focus_file(
            db, t, cid, "j.csv", file(row(10, 1)), declared_version="1.2", now=NOW
        )
        R.create_rule(db, t, "all", "all", 1, "direct", {"application_id": str(apps_id)}, "ann")
    assert admin.main(["allocate", str(t), "2026-01-01", "2026-02-01"]) == 0
    out = capsys.readouterr().out
    assert "succeeded: lines=1 slices=1" in out and "coverage=100.0%" in out
    assert admin.main(["allocate", str(t), "2026-01-01", "2026-02-01"]) == 0
    assert capsys.readouterr().out.startswith("unchanged")
    assert _as and True


def test_the_latest_run_is_decided_by_sequence_not_by_clock(w):
    """Runs that share an identical timestamp must still have one well-defined latest."""
    a, b = str(w.apps["claims"]), str(w.apps["search"])
    with w.session() as db:
        w.load(db, "jan.csv", row(10, 1))
        for target in (a, b, a, b, a):  # five runs with the same 'now'
            w.rule(db, "all", "direct", {"application_id": target})
            assert w.run(db).status == "succeeded"
        by_app = {r["application_id"]: r["effective"] for r in R.allocated_cost_by_application(db)}
        assert by_app == {w.apps["claims"]: 10}
        seqs = [
            r[0] for r in db.execute(text("select seq from allocation_runs order by seq")).all()
        ]
        assert seqs == sorted(set(seqs)) and len(seqs) == 5
