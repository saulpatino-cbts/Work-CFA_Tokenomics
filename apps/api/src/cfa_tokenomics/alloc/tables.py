"""Core table definitions for allocation (migration 0007)."""

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Table, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from ..db import Base

_AMT = Numeric(38, 18)
_TS = DateTime(timezone=True)

allocation_rules = Table(
    "allocation_rules", Base.metadata,
    Column("id", Uuid, primary_key=True), Column("tenant_id", Uuid, nullable=False),
    Column("rule_key", String(128), nullable=False), Column("version", Integer, nullable=False),
    Column("name", Text, nullable=False), Column("priority", Integer, nullable=False),
    Column("enabled", Boolean, nullable=False), Column("method", String(16), nullable=False),
    Column("conditions", JSONB, nullable=False), Column("params", JSONB, nullable=False),
    Column("author", String(1100), nullable=False),
)  # fmt: skip

allocation_drivers = Table(
    "allocation_drivers", Base.metadata,
    Column("id", Uuid, primary_key=True), Column("tenant_id", Uuid, nullable=False),
    Column("rule_key", String(128), nullable=False), Column("application_id", Uuid, nullable=False),
    Column("period_start", _TS, nullable=False), Column("period_end", _TS, nullable=False),
    Column("value", Numeric(38, 12), nullable=False), Column("basis", String(16), nullable=False),
    Column("source", Text, nullable=False), Column("version", Integer, nullable=False),
    Column("author", String(1100), nullable=False),
)  # fmt: skip

allocation_runs = Table(
    "allocation_runs", Base.metadata,
    Column("id", Uuid, primary_key=True), Column("tenant_id", Uuid, nullable=False),
    Column("window_start", _TS, nullable=False), Column("window_end", _TS, nullable=False),
    Column("status", String(16), nullable=False), Column("rules_hash", String(64), nullable=False),
    Column("inputs_hash", String(64), nullable=False), Column("line_count", Integer, nullable=False),
    Column("slice_count", Integer, nullable=False), Column("created_by", String(1100), nullable=False),
    Column("finished_at", _TS), Column("error", Text),
)  # fmt: skip

allocated_costs = Table(
    "allocated_costs", Base.metadata,
    Column("id", Uuid, primary_key=True), Column("tenant_id", Uuid, nullable=False),
    Column("allocation_run_id", Uuid, nullable=False), Column("focus_cost_id", Uuid, nullable=False),
    Column("application_id", Uuid), Column("workload_id", Uuid), Column("rule_key", String(128)),
    Column("rule_version", Integer), Column("method", String(16), nullable=False),
    Column("reason", String(64)), Column("share", _AMT, nullable=False),
    Column("billed_cost", _AMT, nullable=False), Column("effective_cost", _AMT, nullable=False),
    Column("list_cost", _AMT, nullable=False), Column("contracted_cost", _AMT, nullable=False),
    Column("billing_currency", String(3), nullable=False),
)  # fmt: skip
