"""Cost-export connectors end to end against PostgreSQL, as a restricted role. All data is SYNTHETIC;
the export layouts come from documentation and have not been checked against a real export."""

import gzip
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from conftest import app, two_tenants
from sqlalchemy import text
from test_alloc_runner import file, row

from cfa_tokenomics import admin
from cfa_tokenomics.connectors import costexport as cx
from cfa_tokenomics.connectors.store import ObjectInfo, TooLarge

URL = os.environ.get("CFA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")
NOW = datetime(2026, 2, 10, 12, tzinfo=UTC)
OLD = NOW - timedelta(hours=5)


class Store:
    """An in-memory export location. ``put`` with the same key and new bytes models an overwrite."""

    def __init__(self):
        self.files: dict[str, tuple[bytes, str, datetime]] = {}
        self.downloads: list[str] = []
        self._n = 0

    def put(self, key, data: bytes, modified=OLD):
        self._n += 1
        self.files[key] = (data, f"etag{self._n}", modified)

    def list(self, prefix):
        for k, (d, e, m) in sorted(self.files.items()):
            if k.startswith(prefix):
                yield ObjectInfo(k, len(d), e, m)

    def read(self, key, limit):
        self.downloads.append(key)
        d = self.files[key][0]
        if len(d) > limit:
            raise TooLarge(key)
        return d


AWS = {"bucket": "my-exports", "prefix": "cur/focus", "focus_version": "1.2"}
AZURE = {
    "account_url": "https://acct.blob.core.windows.net",
    "container": "exports",
    "prefix": "ea/focus",
}
AWS_RUN = "cur/focus/data/BILLING_PERIOD=2026-01"
AZ_RUN = "ea/focus/20260101-20260131/run1"


def gz(*rows):
    return gzip.compress(file(*rows))


class World:
    def __init__(self, env, provider, scope):
        self.env, self.provider = env, provider
        self.t, self.other = two_tenants(env)
        self.cfg = cx.parse_scope(provider, scope)
        self.store = Store()
        with app(env, self.t) as db:
            self.cid = cx.create_connector(db, self.t, provider, f"{provider}-cost", scope)

    def session(self):
        return app(self.env, self.t)

    def pull(self, now=NOW):
        with self.session() as db:
            return cx.pull(db, self.t, self.cid, self.cfg, self.store, now)

    def total(self):
        with self.session() as db:
            return db.execute(
                text(
                    "select coalesce(sum(effective_cost), 0) from focus_cost_records r where not exists "
                    "(select 1 from focus_supersessions s where s.tenant_id = r.tenant_id and s.record_id = r.id)"
                )
            ).scalar()


@pytest.fixture(params=["aws", "azure"])
def w(env, request):
    scope, where = (AWS, AWS_RUN) if request.param == "aws" else (AZURE, AZ_RUN)
    world = World(env, request.param, scope)
    world.where = where
    return world


def part(w, n):
    return f"{w.where}/part_{n:04d}.csv.gz"


def test_a_run_is_imported_once_and_not_downloaded_again(w):
    w.store.put(part(w, 1), gz(row("100.00", 1), row("50.00", 2)))
    out = w.pull()
    assert [(o.status, o.rows) for o in out] == [("imported", 2)]
    assert w.total() == Decimal(150)
    n = len(w.store.downloads)
    again = w.pull()
    assert [o.status for o in again] == ["already_imported"]
    assert len(w.store.downloads) == n  # nothing was downloaded for an unchanged run
    assert w.total() == Decimal(150)


def test_the_parts_of_one_run_are_one_logical_file_and_do_not_supersede_each_other(w):
    # Two parts hold different rows for the same account and window, as a split export does.
    w.store.put(part(w, 1), gz(row("100.00", 1)))
    w.store.put(part(w, 2), gz(row("40.00", 1), row("10.00", 2)))
    out = w.pull()
    assert [(o.status, o.rows, o.superseded) for o in out] == [("imported", 3, 0)]
    assert w.total() == Decimal(150)  # importing the parts one by one would have kept only the last


def test_a_revised_export_supersedes_and_keeps_history(w):
    w.store.put(part(w, 1), gz(row("100.00", 1), row("50.00", 2)))
    w.pull()
    w.store.put(
        part(w, 1), gz(row("90.00", 1), row("50.00", 2), row("5.00", 3))
    )  # overwritten in place
    out = w.pull()
    assert [(o.status, o.rows, o.superseded) for o in out] == [("imported", 3, 2)]
    assert w.total() == Decimal(145)
    with w.session() as db:
        assert (
            db.execute(text("select count(*) from focus_cost_records")).scalar() == 5
        )  # history stays


def test_a_run_whose_files_changed_minutes_ago_is_deferred(w):
    w.store.put(part(w, 1), gz(row("100.00", 1)), modified=NOW - timedelta(minutes=5))
    out = w.pull()
    assert [o.status for o in out] == ["deferred"] and w.store.downloads == []
    assert w.total() == 0
    later = w.pull(NOW + timedelta(hours=1))
    assert [o.status for o in later] == ["imported"]


def test_mismatched_columns_oversize_and_parquet_import_nothing_and_say_why(w):
    w.store.put(part(w, 1), gz(row("1.00", 1)))
    w.store.put(part(w, 2), gzip.compress(b"BilledCost,ChargeCategory\n1,Usage\n"))
    out = w.pull()
    assert out[0].status == "failed" and "different columns" in out[0].detail
    assert w.total() == 0

    small = World.__new__(World)  # same world with a tiny size cap
    small.__dict__.update(w.__dict__)
    small.cfg = cx.CostExportConfig(**{**w.cfg.__dict__, "max_run_mb": 1})
    w.store.files.clear()
    w.store.put(
        f"{w.where}/part_0001.csv.gz", gzip.compress(file(row("1.00", 1)) + b"x" * 2_000_000)
    )
    assert small.pull()[0].status == "too_large"

    w.store.files.clear()
    w.store.put(f"{w.where}/part_0001.parquet", b"PAR1")
    out = w.pull()
    assert out[0].status == "unsupported" and "CSV" in out[0].detail


def test_a_run_that_failed_is_not_retried_until_its_files_change(w):
    bad = gzip.compress(file(row("not-a-number", 1)))  # parses as a CSV with a rejected row
    w.store.put(part(w, 1), bad)
    first = w.pull()
    assert first[0].status == "failed" and "rejected" in first[0].detail
    n = len(w.store.downloads)
    again = w.pull()
    assert (
        again[0].status == "failed_before" and len(w.store.downloads) == n
    )  # no repeated download
    w.store.put(part(w, 1), gz(row("1.00", 1)))  # the export was fixed
    assert w.pull()[0].status == "imported"


def test_only_the_newest_run_of_a_period_is_read(env):
    w = World(env, "azure", AZURE)
    w.store.put(
        "ea/focus/20260101-20260131/run1/p.csv.gz",
        gz(row("100.00", 1)),
        modified=OLD - timedelta(days=1),
    )
    w.store.put(
        "ea/focus/20260101-20260131/run2/p.csv.gz",
        gz(row("100.00", 1), row("20.00", 2)),
        modified=OLD,
    )
    out = w.pull()
    assert [(o.run_id, o.status) for o in out] == [("run2", "imported")]
    assert w.store.downloads == ["ea/focus/20260101-20260131/run2/p.csv.gz"]
    assert w.total() == Decimal(120)


def test_finality_follows_each_clouds_own_revision_window(env):
    for provider, scope, where, days_after, expect in (
        ("azure", AZURE, AZ_RUN, 10, "final"),  # 7-day rule: January ended 10 days before
        ("aws", AWS, AWS_RUN, 10, "provisional"),  # two-week rule: not yet
    ):
        w = World(env, provider, scope)
        w.store.put(
            f"{where}/p.csv.gz", gz(row("1.00", 31)), modified=datetime(2026, 1, 31, 12, tzinfo=UTC)
        )
        now = datetime(2026, 2, 1, tzinfo=UTC) + timedelta(days=days_after - 1)
        w.pull(now)
        with w.session() as db:
            got = db.execute(
                text("select finality from ingestion_runs where status = 'succeeded'")
            ).scalar()
        assert got == expect, provider
        with env.begin() as c:
            c.execute(text("delete from focus_supersessions"))


def test_one_tenant_never_sees_anothers_imported_cost(env):
    w = World(env, "aws", AWS)
    w.store.put(f"{AWS_RUN}/p.csv.gz", gz(row("100.00", 1)))
    w.pull()
    with app(env, w.other) as db:
        assert db.execute(text("select count(*) from focus_cost_records")).scalar() == 0
        assert db.execute(text("select count(*) from connectors")).scalar() == 0


def test_the_connector_stores_no_credential_and_refuses_one(env):
    t, _ = two_tenants(env)
    with app(env, t) as db:
        cid = cx.create_connector(db, t, "aws", "c1", AWS)
        row_ = db.execute(
            text("select credential_ref, scope::text from connectors where id = :i"), {"i": cid}
        ).one()
        assert row_[0] is None
        for bad in ({**AWS, "secret_access_key": "x"}, {**AWS, "session_token": "x"}):
            with pytest.raises(cx.ConfigError):
                cx.create_connector(db, t, "aws", "c2", bad)
        db.rollback()
        assert db.execute(text("select count(*) from connectors")).scalar() == 1


def test_status_reports_the_last_success_and_failure(w):
    w.store.put(part(w, 1), gz(row("100.00", 1)))
    w.pull()
    with w.session() as db:
        st = cx.connector_status(db, w.cid)
    assert st["last_success"]["rows"] == 1 and st["last_failure"] is None


def test_the_cli_adds_checks_and_runs_a_connector(env, tmp_path, capsys, monkeypatch):
    t, _ = two_tenants(env)
    scope = tmp_path / "scope.json"
    scope.write_text('{"bucket": "my-exports", "prefix": "cur/focus"}')
    assert admin.main(["connector-add", "aws", str(t), "cli-aws", str(scope)]) == 0
    assert len(capsys.readouterr().out.strip()) == 36
    scope.write_text('{"bucket": "my-exports", "access_key": "x"}')
    assert admin.main(["connector-add", "aws", str(t), "cli-bad", str(scope)]) == 1
    assert "refused" in capsys.readouterr().err

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(
        cx, "datetime", Frozen
    )  # the CLI uses the clock; pin it inside the lookback
    store = Store()
    store.put(f"{AWS_RUN}/p.csv.gz", gz(row("100.00", 1)))
    monkeypatch.setattr(cx, "build_store", lambda cfg: store)
    assert admin.main(["connector-check", str(t), "cli-aws"]) == 0
    assert "ok   data" in capsys.readouterr().out
    assert admin.main(["connector-run", str(t), "cli-aws", "--dry-run"]) == 0
    assert "would read 2026-01" in capsys.readouterr().out
    assert store.downloads == []
    assert admin.main(["connector-run", str(t), "cli-aws"]) == 0
    assert "imported rows=1" in capsys.readouterr().out
    assert admin.main(["connector-status", str(t), "cli-aws"]) == 0
    assert '"rows": 1' in capsys.readouterr().out
    assert admin.main(["connector-run", str(t), "no-such"]) == 1
