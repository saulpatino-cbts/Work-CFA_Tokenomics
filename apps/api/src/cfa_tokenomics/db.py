"""Database schema and engine (ADR 0006). Schema changes go through Alembic migrations."""

from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import Depends
from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import Settings, get_settings


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class RoleAssignment(Base):
    """A role granted to an identity. Identity is issuer + subject, never email."""

    __tablename__ = "role_assignments"
    issuer: Mapped[str] = mapped_column(String(512), primary_key=True)
    subject: Mapped[str] = mapped_column(String(512), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by: Mapped[str] = mapped_column(String(1100), nullable=False)


class AuditEvent(Base):
    """Append-only record of security-relevant actions. Never stores secrets or bearer values."""

    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    actor: Mapped[str] = mapped_column(String(1100), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(1100), nullable=False)
    detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class RequestObservationRow(Base):
    """One model-call attempt routed through the app. Replays are idempotent via source_key."""

    __tablename__ = "usage_request_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String(1300), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    account: Mapped[str] = mapped_column(String(256), nullable=False)
    model_id: Mapped[str] = mapped_column(String(256), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(BigInteger)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger)
    cache_read_tokens: Mapped[int | None] = mapped_column(BigInteger)
    cache_write_tokens: Mapped[int | None] = mapped_column(BigInteger)
    reasoning_tokens: Mapped[int | None] = mapped_column(BigInteger)
    provider_total: Mapped[int | None] = mapped_column(BigInteger)
    quality: Mapped[str] = mapped_column(String(16), nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(32), nullable=False)
    usage_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AggregateObservationRow(Base):
    """A provider metric window. A revised value replaces the old one and bumps revision."""

    __tablename__ = "usage_aggregate_observations"
    __table_args__ = (
        UniqueConstraint(
            "provider", "account", "model_id", "category", "window_start", "window_end", "statistic"
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    account: Mapped[str] = mapped_column(String(256), nullable=False)
    model_id: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    statistic: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    quality: Mapped[str] = mapped_column(String(16), nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(32), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CollectionCheckpoint(Base):
    """Cursor per (provider, account). Advanced only after observations are durably written."""

    __tablename__ = "collection_checkpoints"
    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    account: Mapped[str] = mapped_column(String(256), primary_key=True)
    cursor: Mapped[str | None] = mapped_column(String(2048))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


_engines: dict[str, Engine] = {}


def get_engine(settings: Settings) -> Engine | None:
    if settings.database_url is None:
        return None
    url = settings.database_url.get_secret_value()
    if url not in _engines:
        _engines[url] = create_engine(url, pool_pre_ping=True)
    return _engines[url]


def get_session(settings: Settings = Depends(get_settings)) -> Iterator[Session]:
    engine = get_engine(settings)
    if engine is None:
        raise RuntimeError("database not configured")
    with sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
