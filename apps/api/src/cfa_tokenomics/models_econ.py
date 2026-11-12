"""ORM models for the economics core (migration 0005).

Tenant-owned tables are protected by row-level security. These models add no tenant filters;
the database enforces isolation."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, _now

_MONEY = Numeric(28, 10)
_QTY = Numeric(38, 12)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    base_currency: Mapped[str] = mapped_column(String(3))
    fiscal_year_start_month: Mapped[int] = mapped_column(SmallInteger, default=1)
    person_display: Mapped[str] = mapped_column(String(12), default="pseudonym")


class Person(Base):
    """A pseudonym's display name (ADR 0013). A name and nothing else; see migration 0011."""

    __tablename__ = "people"
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    pseudonym: Mapped[str] = mapped_column(String(34), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(256))
    source: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class _Owned:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid)


class BusinessUnit(_Owned, Base):
    __tablename__ = "business_units"
    name: Mapped[str] = mapped_column(String(256))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    cost_center: Mapped[str | None] = mapped_column(String(128))


class Customer(_Owned, Base):
    __tablename__ = "customers"
    name: Mapped[str] = mapped_column(String(256))
    segment: Mapped[str | None] = mapped_column(String(128))
    external_ref: Mapped[str | None] = mapped_column(String(256))


class Environment(_Owned, Base):
    __tablename__ = "environments"
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16))


class Application(_Owned, Base):
    __tablename__ = "applications"
    name: Mapped[str] = mapped_column(String(256))
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    owner: Mapped[str | None] = mapped_column(String(256))
    lifecycle: Mapped[str] = mapped_column(String(8), default="run")
    currency: Mapped[str] = mapped_column(String(3))
    initial_investment: Mapped[Decimal | None] = mapped_column(_MONEY)
    investment_basis: Mapped[str | None] = mapped_column(String(16))
    amortization_months: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)


class Workload(_Owned, Base):
    __tablename__ = "workloads"
    application_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    environment_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(String(256))
    kind: Mapped[str] = mapped_column(String(16))


class PriceBook(_Owned, Base):
    __tablename__ = "price_books"
    name: Mapped[str] = mapped_column(String(256))
    currency: Mapped[str] = mapped_column(String(3))
    source: Mapped[str] = mapped_column(String(24))


class PriceEntry(_Owned, Base):
    __tablename__ = "price_entries"
    price_book_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    provider: Mapped[str] = mapped_column(String(64))
    model_key: Mapped[str] = mapped_column(String(256))
    measure: Mapped[str] = mapped_column(String(32))
    unit_price: Mapped[Decimal] = mapped_column(_MONEY)
    per_quantity: Mapped[Decimal] = mapped_column(_QTY, default=Decimal(1_000_000))
    currency: Mapped[str] = mapped_column(String(3))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inclusion_rule: Mapped[str | None] = mapped_column(String(256))
    note: Mapped[str | None] = mapped_column(Text)


class ValueAssumption(_Owned, Base):
    """Append-only: a change is a new version, never an update."""

    __tablename__ = "value_assumptions"
    application_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[Decimal | None] = mapped_column(_QTY)
    unit: Mapped[str] = mapped_column(String(32))
    basis: Mapped[str] = mapped_column(String(16))
    rationale: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(1100))
    version: Mapped[int] = mapped_column(Integer)


class Scenario(_Owned, Base):
    __tablename__ = "scenarios"
    application_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(String(256))
    kind: Mapped[str] = mapped_column(String(24))
    base_scenario_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(16), default="draft")


class ScenarioDriver(_Owned, Base):
    __tablename__ = "scenario_drivers"
    scenario_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    driver_key: Mapped[str] = mapped_column(String(128))
    value: Mapped[Decimal | None] = mapped_column(_QTY)
    unit: Mapped[str] = mapped_column(String(32))
    basis: Mapped[str] = mapped_column(String(16))


class CalcNodeRow(Base):
    """Append-only calculation node. The id is a content hash, so a stored node can be verified."""

    __tablename__ = "calculation_nodes"
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    key: Mapped[str] = mapped_column(String(256))
    formula_id: Mapped[str] = mapped_column(String(128))
    formula_version: Mapped[int] = mapped_column(Integer)
    value: Mapped[Decimal | None] = mapped_column(Numeric)
    unit: Mapped[str] = mapped_column(String(64))
    currency: Mapped[str | None] = mapped_column(String(3))
    mix_observed: Mapped[Decimal] = mapped_column(Numeric)
    mix_estimated: Mapped[Decimal] = mapped_column(Numeric)
    mix_assumed: Mapped[Decimal] = mapped_column(Numeric)
    status: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text, default="")
    label: Mapped[str] = mapped_column(Text, default="")
    source_ref: Mapped[str | None] = mapped_column(String(256))


class CalcEdgeRow(Base):
    __tablename__ = "calculation_edges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "parent_id"], ["calculation_nodes.tenant_id", "calculation_nodes.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "child_id"], ["calculation_nodes.tenant_id", "calculation_nodes.id"]
        ),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    parent_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    child_id: Mapped[str] = mapped_column(String(16))
