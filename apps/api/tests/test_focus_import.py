"""FOCUS import against real PostgreSQL, as a restricted role. All files are SYNTHETIC."""

import gzip
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from conftest import app, two_tenants
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from cfa_tokenomics import admin, migrate
from cfa_tokenomics.focus import importer
from cfa_tokenomics.focus import tables as T
from cfa_tokenomics.focus.importer import current_cost_summary, import_focus_file

URL = os.environ.get("CFA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")

HEAD = (
    "BilledCost,EffectiveCost,ListCost,ContractedCost,ChargeCategory,ChargePeriodStart,"
    "ChargePeriodEnd,BillingCurrency,BillingAccountId,SubAccountId,ServiceName,x_Extra"
)
NOW = datetime(2026, 1, 5, tzinfo=UTC)


def line(amount, day, *, cur="USD", cat="Usage", acct="ba1", sub="sub1", eff=None, svc="Bedrock"):
    eff = amount if eff is None else eff
    start, end = f"2026-01-{day:02d}T00:00:00Z", f"2026-01-{day + 1:02d}T00:00:00Z"
    return (
        f"{amount},{eff},{amount},{amount},{cat},{start},{end},{cur},{acct},{sub},{svc},extra-{day}"
    )


def file(*rows, head=HEAD):
    return ("\n".join([head, *rows]) + "\n").encode()


def go(db, tid, cid, name, content, **kw):
    kw.setdefault("now", NOW)
    return import_focus_file(db, tid, cid, name, content, declared_version="1.2", **kw)


def setup(env):
    a, b = two_tenants(env)
    with app(env, a) as db:
        cid = importer.get_or_create_manual_connector(db, a)
    return a, b, cid


def total(db, currency="USD"):
    return sum(
        (r["billed"] for r in current_cost_summary(db) if r["currency"] == currency), Decimal(0)
    )


def test_import_lands_records_with_lineage_basis_and_the_raw_file(env):
    a, _, cid = setup(env)
    content = file(line(10, 1), line(20, 2), line(30, 3))
    with app(env, a) as db:
        res = go(db, a, cid, "jan.csv", content)
        assert (res.status, res.rows_imported, res.rows_rejected) == ("succeeded", 3, 0)
        assert res.unknown_columns == ["x_Extra"]
        recs = db.execute(
            select(T.focus_cost_records).order_by(T.focus_cost_records.c.row_number)
        ).all()
        assert [r.row_number for r in recs] == [2, 3, 4]
        assert {r.basis for r in recs} == {"observed"} and {
            r.source_focus_version for r in recs
        } == {"1.2"}
        assert recs[0].extensions == {"x_Extra": "extra-1"}
        raw = db.execute(select(T.raw_files)).one()
        assert raw.id == recs[0].raw_file_id and raw.size_bytes == len(content)
        assert (
            gzip.decompress(raw.content_gzip) == content
        )  # the original file is kept byte for byte
        run = db.execute(select(T.ingestion_runs)).one()
        assert (run.status, run.row_count, run.mapper_version) == ("succeeded", 3, "focus-csv-1")


def test_amounts_are_stored_exactly(env):
    a, _, cid = setup(env)
    row = "0.123456789012345678,1,1,1,Usage,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,USD,ba1,sub1,S,x"
    with app(env, a) as db:
        assert go(db, a, cid, "x.csv", file(row)).status == "succeeded"
        assert db.execute(select(T.focus_cost_records.c.billed_cost)).scalar() == Decimal(
            "0.123456789012345678"
        )


def test_the_same_file_is_imported_only_once(env):
    a, _, cid = setup(env)
    content = file(line(10, 1))
    with app(env, a) as db:
        first = go(db, a, cid, "jan.csv", content)
        again = go(db, a, cid, "renamed.csv", content)
        assert again.status == "duplicate" and again.duplicate_of == first.run_id
        assert db.scalar(select(func.count()).select_from(T.focus_cost_records)) == 1
        assert db.scalar(select(func.count()).select_from(T.ingestion_runs)) == 1


def test_a_file_with_a_rejected_row_is_refused_whole_by_default(env):
    a, _, cid = setup(env)
    content = file(line(10, 1), line(20, 2, cat="Rebate"), line(30, 3))
    with app(env, a) as db:
        res = go(db, a, cid, "bad.csv", content)
        assert res.status == "failed" and res.reject_reasons == {"unknown_charge_category": 1}
        assert db.scalar(select(func.count()).select_from(T.focus_cost_records)) == 0
        rj = db.execute(select(T.ingestion_rejects)).one()
        assert (rj.row_number, rj.reason, rj.column_name) == (
            3,
            "unknown_charge_category",
            "ChargeCategory",
        )
        assert set(rj._fields) == {
            "id",
            "tenant_id",
            "ingestion_run_id",
            "row_number",
            "reason",
            "column_name",
        }


def test_allow_partial_imports_the_good_rows_and_a_failed_file_can_be_retried(env):
    a, _, cid = setup(env)
    content = file(line(10, 1), line(20, 2, cat="Rebate"), line(30, 3))
    with app(env, a) as db:
        assert go(db, a, cid, "bad.csv", content).status == "failed"
        res = go(
            db, a, cid, "bad.csv", content, allow_partial=True
        )  # a failed attempt does not block a retry
        assert (res.status, res.rows_imported, res.rows_rejected) == ("partial", 2, 1)
        assert total(db) == 40


def test_a_revised_export_replaces_the_same_window_and_keeps_history(env):
    a, _, cid = setup(env)
    with app(env, a) as db:
        go(db, a, cid, "v1.csv", file(line(10, 1), line(20, 2), line(30, 3)))
        assert total(db) == 60
        res = go(db, a, cid, "v2.csv", file(line(11, 1), line(21, 2), line(31, 3)))
        assert (res.status, res.superseded) == ("succeeded", 3)
        assert total(db) == 63  # replaced, not added to 123
        assert (
            db.scalar(select(func.count()).select_from(T.focus_cost_records)) == 6
        )  # history is kept
        assert db.scalar(select(func.count()).select_from(T.focus_supersessions)) == 3


def test_a_daily_slice_replaces_only_its_own_day(env):
    a, _, cid = setup(env)
    with app(env, a) as db:
        go(db, a, cid, "mtd.csv", file(line(10, 1), line(20, 2), line(30, 3)))
        res = go(db, a, cid, "day2.csv", file(line(25, 2)))
        assert res.superseded == 1 and total(db) == 10 + 25 + 30


def test_supersession_is_scoped_to_account_pair_and_connector(env):
    a, _, cid = setup(env)
    with app(env, a) as db:
        go(db, a, cid, "both.csv", file(line(10, 1, sub="sub1"), line(7, 1, sub="sub2")))
        go(db, a, cid, "only-sub1.csv", file(line(12, 1, sub="sub1")))
        assert total(db) == 12 + 7  # sub2 untouched
        from cfa_tokenomics.models_econ import Tenant  # noqa: F401

        other = importer.get_or_create_manual_connector(db, a, name="second-connector")
        go(db, a, other, "other.csv", file(line(99, 1, sub="sub1")))
        assert (
            total(db) == 12 + 7 + 99
        )  # another connector's data is a different source, not a revision


def test_currencies_are_never_combined_and_billed_and_effective_stay_separate(env):
    a, _, cid = setup(env)
    purchase = line(1000, 1, cat="Purchase", eff=0)
    usage = [line(0, d, eff=100) for d in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)]
    with app(env, a) as db:
        go(db, a, cid, "mix.csv", file(purchase, *usage, line(50, 1, cur="EUR")))
        s = current_cost_summary(db)
        usd = [r for r in s if r["currency"] == "USD"]
        assert {r["currency"] for r in s} == {"USD", "EUR"}
        assert sum(r["billed"] for r in usd) == 1000 and sum(r["effective"] for r in usd) == 1000
        by_cat = {r["charge_category"]: r for r in usd}
        assert (by_cat["Purchase"]["billed"], by_cat["Purchase"]["effective"]) == (1000, 0)
        assert (by_cat["Usage"]["billed"], by_cat["Usage"]["effective"]) == (0, 1000)
        assert [r["billed"] for r in s if r["currency"] == "EUR"] == [50]


def test_missing_columns_fail_the_file_but_keep_a_record_of_the_attempt(env):
    a, _, cid = setup(env)
    with app(env, a) as db:
        res = go(db, a, cid, "no.csv", b"BilledCost,BillingCurrency\n1,USD\n")
        assert res.status == "failed" and "missing required columns" in res.error
        assert db.scalar(select(func.count()).select_from(T.focus_cost_records)) == 0
        assert (
            db.execute(select(T.ingestion_runs.c.status, T.ingestion_runs.c.error)).one()[0]
            == "failed"
        )
        assert db.scalar(select(func.count()).select_from(T.raw_files)) == 1


def test_an_invalid_declared_version_fails_cleanly(env):
    a, _, cid = setup(env)
    with app(env, a) as db:
        res = import_focus_file(
            db, a, cid, "x.csv", file(line(1, 1)), declared_version="9.9", now=NOW
        )
        assert res.status == "failed" and "version" in res.error


def test_a_failure_part_way_leaves_no_partial_data_and_no_supersession(env, monkeypatch):
    a, _, cid = setup(env)
    with app(env, a) as db:
        go(db, a, cid, "v1.csv", file(line(10, 1), line(20, 2)))
        real, calls = importer._record, {"n": 0}

        def flaky(r, base):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("simulated crash")
            return real(r, base)

        monkeypatch.setattr(importer, "_record", flaky)
        res = go(db, a, cid, "v2.csv", file(line(11, 1), line(21, 2)))
        assert res.status == "failed" and res.error == "import failed: RuntimeError"
        monkeypatch.setattr(importer, "_record", real)
        assert total(db) == 30  # v1 is still current and complete
        assert db.scalar(select(func.count()).select_from(T.focus_cost_records)) == 2
        assert db.scalar(select(func.count()).select_from(T.focus_supersessions)) == 0


def test_finality_follows_the_revision_window_unless_set(env):
    a, _, cid = setup(env)
    with app(env, a) as db:
        recent = go(db, a, cid, "r.csv", file(line(1, 1)), now=datetime(2026, 1, 5, tzinfo=UTC))
        assert (
            db.execute(
                select(T.ingestion_runs.c.finality).where(T.ingestion_runs.c.id == recent.run_id)
            ).scalar()
            == "provisional"
        )
        old = go(db, a, cid, "o.csv", file(line(2, 1)), now=datetime(2026, 2, 1, tzinfo=UTC))
        assert (
            db.execute(
                select(T.ingestion_runs.c.finality).where(T.ingestion_runs.c.id == old.run_id)
            ).scalar()
            == "final"
        )
        forced = go(db, a, cid, "f.csv", file(line(3, 1)), finality="final")
        assert (
            db.execute(
                select(T.focus_cost_records.c.finality).where(
                    T.focus_cost_records.c.ingestion_run_id == forced.run_id
                )
            )
            .scalars()
            .first()
            == "final"
        )


def test_tenants_cannot_see_or_import_into_each_others_cost_data(env):
    a, b, cid = setup(env)
    with app(env, a) as db:
        go(db, a, cid, "jan.csv", file(line(10, 1)))
    with app(env, b) as db:
        assert current_cost_summary(db) == []
        assert db.scalar(select(func.count()).select_from(T.raw_files)) == 0
        with pytest.raises((IntegrityError, DBAPIError)):
            go(db, b, cid, "jan.csv", file(line(10, 1)))  # A's connector id does not exist for B


def test_the_runtime_role_cannot_edit_or_delete_cost_history(env):
    a, _, cid = setup(env)
    with app(env, a) as db:
        go(db, a, cid, "jan.csv", file(line(10, 1)))
    for stmt in (
        "update focus_cost_records set billed_cost = 0",
        "delete from focus_cost_records",
        "delete from focus_supersessions",
        "update raw_files set filename = 'x'",
    ):
        with app(env, a) as db, pytest.raises(DBAPIError, match="permission denied"):
            db.execute(text(stmt))


def test_a_cost_row_must_belong_to_its_run_and_file_in_the_same_tenant(env):
    a, b, cid = setup(env)
    with app(env, a) as db:
        res = go(db, a, cid, "jan.csv", file(line(10, 1)))
        raw_id = db.execute(select(T.raw_files.c.id)).scalar()
    from sqlalchemy.orm import Session

    with (
        Session(env) as admin_db,
        pytest.raises(IntegrityError, match="fk_focus"),
    ):  # superuser: FKs still hold
        admin_db.execute(
            text(
                "insert into focus_cost_records (id, tenant_id, ingestion_run_id, raw_file_id, row_number, billed_cost,"
                " effective_cost, list_cost, contracted_cost, charge_category, charge_period_start, charge_period_end,"
                " billing_currency, extensions, basis, finality, source_focus_version, mapper_version)"
                " values (gen_random_uuid(), :b, :run, :raw, 2, 1, 1, 1, 1, 'Usage', now(), now() + interval '1 day',"
                " 'USD', '{}', 'observed', 'final', '1.2', 'x')"
            ),
            {"b": b, "run": res.run_id, "raw": raw_id},
        )
        admin_db.commit()


def test_database_constraints_reject_bad_cost_rows_even_from_a_privileged_writer(env):
    a, _, cid = setup(env)
    with app(env, a) as db:
        res = go(db, a, cid, "jan.csv", file(line(10, 1)))
        raw_id = db.execute(select(T.raw_files.c.id)).scalar()
    from sqlalchemy.orm import Session

    def insert(category="Usage", end="now() + interval '1 day'", cur="'USD'"):
        return text(
            "insert into focus_cost_records (id, tenant_id, ingestion_run_id, raw_file_id, row_number, billed_cost,"
            " effective_cost, list_cost, contracted_cost, charge_category, charge_period_start, charge_period_end,"
            " billing_currency, extensions, basis, finality, source_focus_version, mapper_version)"
            f" values (gen_random_uuid(), :t, :run, :raw, 9, 1, 1, 1, 1, '{category}', now(), {end}, {cur},"
            " '{}', 'observed', 'final', '1.2', 'x')"
        )

    p = {"t": a, "run": res.run_id, "raw": raw_id}
    for kwargs, name in (
        ({"category": "Rebate"}, "ck_focus_category"),
        ({"end": "now() - interval '1 day'"}, "ck_focus_period"),
        ({"cur": "'US'"}, "ck_focus_currency"),
    ):
        with Session(env) as admin_db, pytest.raises(IntegrityError, match=name):
            admin_db.execute(insert(**kwargs), p)
            admin_db.commit()


def test_downgrade_removes_the_cost_layer_and_upgrade_restores_it(env):
    migrate.main(["downgrade", "0005"])
    with env.connect() as c:
        names = {
            r[0]
            for r in c.execute(text("select tablename from pg_tables where schemaname='public'"))
        }
    assert "focus_cost_records" not in names and "applications" in names
    migrate.main(["upgrade"])


def test_cli_import_focus(env, tmp_path, capsys):
    a, _ = two_tenants(env)
    path = tmp_path / "jan.csv"
    path.write_bytes(file(line(10, 1), line(20, 2)))
    assert admin.main(["import-focus", str(a), str(path), "--version", "1.2"]) == 0
    assert "succeeded: imported=2 rejected=0" in capsys.readouterr().out
    assert admin.main(["import-focus", str(a), str(path), "--version", "1.2"]) == 0
    assert capsys.readouterr().out.startswith("duplicate")
    bad = tmp_path / "bad.csv"
    bad.write_bytes(b"nope\n1\n")
    assert admin.main(["import-focus", str(a), str(bad)]) == 1
    assert uuid.UUID(str(a))
