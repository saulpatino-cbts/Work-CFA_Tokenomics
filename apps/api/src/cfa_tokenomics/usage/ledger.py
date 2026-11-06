"""Durable, replay-safe writes for usage observations (ADR 0007)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..db import (
    AggregateObservationRow,
    CollectionCheckpoint,
    RequestObservationRow,
)
from .models import AggregateObservation, RequestObservation


def record_request(db: Session, obs: RequestObservation) -> bool:
    """Insert once per source_key. Returns True if inserted, False if it was a replay."""
    stmt = (
        insert(RequestObservationRow)
        .values(
            source_key=obs.source_key,
            provider=obs.provider,
            account=obs.account,
            model_id=obs.model_id,
            occurred_at=obs.occurred_at,
            input_tokens=obs.input,
            output_tokens=obs.output,
            cache_read_tokens=obs.cache_read,
            cache_write_tokens=obs.cache_write,
            reasoning_tokens=obs.reasoning,
            provider_total=obs.total,
            quality=obs.quality.value,
            normalization_version=obs.normalization_version,
            usage_metadata=obs.metadata,
        )
        .on_conflict_do_nothing(index_elements=["source_key"])
        .returning(RequestObservationRow.id)
    )
    inserted = db.execute(stmt).scalar() is not None
    db.commit()
    return inserted


def upsert_aggregate(db: Session, obs: AggregateObservation) -> str:
    """Write a provider window. Returns 'inserted', 'unchanged' or 'revised'."""
    row = db.scalar(
        select(AggregateObservationRow).where(
            AggregateObservationRow.provider == obs.provider,
            AggregateObservationRow.account == obs.account,
            AggregateObservationRow.model_id == obs.model_id,
            AggregateObservationRow.category == obs.category,
            AggregateObservationRow.window_start == obs.window_start,
            AggregateObservationRow.window_end == obs.window_end,
            AggregateObservationRow.statistic == obs.statistic,
        )
    )
    if row is None:
        db.add(
            AggregateObservationRow(
                provider=obs.provider,
                account=obs.account,
                model_id=obs.model_id,
                category=obs.category,
                window_start=obs.window_start,
                window_end=obs.window_end,
                statistic=obs.statistic,
                value=obs.value,
                quality=obs.quality.value,
                normalization_version=obs.normalization_version,
                revision=1,
            )
        )
        db.commit()
        return "inserted"
    if row.value == obs.value and row.quality == obs.quality.value:
        return "unchanged"
    row.value, row.quality = obs.value, obs.quality.value
    row.normalization_version = obs.normalization_version
    row.revision += 1
    row.updated_at = datetime.now(UTC)
    db.commit()
    return "revised"


def save_checkpoint(db: Session, provider: str, account: str, cursor: str | None) -> None:
    """Call only after the observations the cursor covers are committed."""
    stmt = insert(CollectionCheckpoint).values(provider=provider, account=account, cursor=cursor)
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["provider", "account"],
            set_={"cursor": cursor, "updated_at": datetime.now(UTC)},
        )
    )
    db.commit()


def load_checkpoint(db: Session, provider: str, account: str) -> str | None:
    row = db.get(CollectionCheckpoint, (provider, account))
    return row.cursor if row else None
