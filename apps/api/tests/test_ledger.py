"""Ledger writes against real PostgreSQL (CFA_TEST_DATABASE_URL). Data is SYNTHETIC."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from cfa_tokenomics import migrate
from cfa_tokenomics.db import AggregateObservationRow, RequestObservationRow
from cfa_tokenomics.usage import ledger
from cfa_tokenomics.usage.models import AggregateObservation, Quality, RequestObservation

URL = os.environ.get("CFA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="CFA_TEST_DATABASE_URL not set")
T = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("CFA_DATABASE_URL", URL)
    engine = create_engine(URL)
    with engine.begin() as c:
        c.execute(
            text(
                "drop table if exists collection_checkpoints, usage_aggregate_observations, "
                "usage_request_observations, audit_events, role_assignments, alembic_version"
            )
        )
    migrate.main(["upgrade"])
    with Session(engine) as s:
        yield s


def req(**kw):
    base = dict(provider="bedrock", account="a", request_id="r1", attempt=1, model_id="m")
    return RequestObservation(occurred_at=T, **{**base, **kw})


def agg(value=10.0, **kw):
    base = dict(provider="bedrock", account="a", model_id="m", category="input", statistic="Sum")
    return AggregateObservation(
        window_start=T, window_end=T + timedelta(minutes=5), value=value, **{**base, **kw}
    )


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_request_replay_is_idempotent(db):
    assert ledger.record_request(db, req(input=5)) is True
    assert ledger.record_request(db, req(input=5)) is False
    assert count(db, RequestObservationRow) == 1


def test_attempts_are_distinct_rows(db):
    ledger.record_request(db, req(attempt=1, input=5))
    ledger.record_request(db, req(attempt=2, input=5))
    assert count(db, RequestObservationRow) == 2


def test_unknown_categories_are_stored_as_null_not_zero(db):
    ledger.record_request(db, req(input=5))
    row = db.scalar(select(RequestObservationRow))
    assert row.output_tokens is None and row.input_tokens == 5


def test_negative_tokens_rejected_by_database(db):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        ledger.record_request(db, req(input=-1))


def test_aggregate_insert_unchanged_and_revised(db):
    assert ledger.upsert_aggregate(db, agg(10.0)) == "inserted"
    assert ledger.upsert_aggregate(db, agg(10.0)) == "unchanged"
    assert ledger.upsert_aggregate(db, agg(12.0)) == "revised"
    row = db.scalar(select(AggregateObservationRow))
    assert (row.value, row.revision) == (12.0, 2)
    assert count(db, AggregateObservationRow) == 1  # late revision never inflates totals


def test_partial_then_complete_revises_quality(db):
    ledger.upsert_aggregate(db, agg(5.0, quality=Quality.PARTIAL))
    assert ledger.upsert_aggregate(db, agg(8.0, quality=Quality.REPORTED)) == "revised"
    assert db.scalar(select(AggregateObservationRow)).quality == "reported"


def test_checkpoint_roundtrip_and_overwrite(db):
    assert ledger.load_checkpoint(db, "bedrock", "a") is None
    ledger.save_checkpoint(db, "bedrock", "a", "c1")
    ledger.save_checkpoint(db, "bedrock", "a", "c2")
    assert ledger.load_checkpoint(db, "bedrock", "a") == "c2"


def test_migration_0002_downgrades_cleanly(db):
    migrate.main(["downgrade", "0001"])
    with db.bind.connect() as c:
        names = {r[0] for r in c.execute(text("select tablename from pg_tables"))}
    assert "usage_request_observations" not in names and "role_assignments" in names
    migrate.main(["upgrade"])
