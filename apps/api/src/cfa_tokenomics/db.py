"""Database schema and engine (ADR 0006). Schema changes go through Alembic migrations."""

from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import Depends
from sqlalchemy import JSON, DateTime, Integer, String, create_engine
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
