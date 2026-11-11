"""Core table definitions for the FOCUS cost layer (migration 0006). Core, not ORM: wide rows are
written in bulk."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Table,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

from ..db import Base

_AMT = Numeric(38, 18)
_TS = DateTime(timezone=True)

connectors = Table(
    "connectors", Base.metadata,
    Column("id", Uuid, primary_key=True), Column("tenant_id", Uuid, nullable=False),
    Column("provider_key", String(64), nullable=False), Column("kind", String(16), nullable=False),
    Column("name", String(256), nullable=False), Column("credential_ref", String(512)),
    Column("scope", JSONB, nullable=False), Column("enabled", Boolean, nullable=False),
)  # fmt: skip

ingestion_runs = Table(
    "ingestion_runs", Base.metadata,
    Column("id", Uuid, primary_key=True), Column("tenant_id", Uuid, nullable=False),
    Column("connector_id", Uuid, nullable=False), Column("source_name", Text, nullable=False),
    Column("declared_version", String(16), nullable=False), Column("status", String(16), nullable=False),
    Column("started_at", _TS), Column("finished_at", _TS), Column("row_count", Integer, nullable=False),
    Column("rejected_count", Integer, nullable=False), Column("mapper_version", String(32), nullable=False),
    Column("content_hash", String(64), nullable=False), Column("finality", String(12), nullable=False),
    Column("error", Text),
)  # fmt: skip

raw_files = Table(
    "raw_files", Base.metadata,
    Column("id", Uuid, primary_key=True), Column("tenant_id", Uuid, nullable=False),
    Column("ingestion_run_id", Uuid, nullable=False), Column("filename", Text, nullable=False),
    Column("content_hash", String(64), nullable=False), Column("size_bytes", BigInteger, nullable=False),
    Column("content_gzip", LargeBinary, nullable=False),
)  # fmt: skip

ingestion_rejects = Table(
    "ingestion_rejects", Base.metadata,
    Column("id", Uuid, primary_key=True), Column("tenant_id", Uuid, nullable=False),
    Column("ingestion_run_id", Uuid, nullable=False), Column("row_number", Integer, nullable=False),
    Column("reason", String(64), nullable=False), Column("column_name", String(128)),
)  # fmt: skip

AMOUNT_COLUMNS = (
    "billed_cost", "effective_cost", "list_cost", "contracted_cost", "list_unit_price",
    "contracted_unit_price", "consumed_quantity", "pricing_quantity", "commitment_discount_quantity",
)  # fmt: skip
TIMESTAMP_COLUMNS = (
    "charge_period_start", "charge_period_end", "billing_period_start", "billing_period_end",
)  # fmt: skip
TEXT_COLUMNS = (
    "billing_account_id", "billing_account_name", "sub_account_id", "sub_account_name", "charge_class",
    "charge_description", "charge_frequency", "pricing_category", "consumed_unit", "pricing_unit",
    "service_name", "service_category", "service_subcategory", "service_provider_name",
    "host_provider_name", "invoice_issuer_name", "invoice_id", "resource_id", "resource_name",
    "resource_type", "region_id", "region_name", "availability_zone", "sku_id", "sku_price_id",
    "sku_meter", "commitment_discount_id", "commitment_discount_name", "commitment_discount_category",
    "commitment_discount_type", "commitment_discount_status", "commitment_discount_unit",
    "allocated_method_id", "allocated_resource_id", "allocated_resource_name",
)  # fmt: skip
JSON_COLUMNS = ("tags", "sku_price_details", "allocated_method_details", "allocated_tags")
SHORT_COLUMNS = ("charge_category", "billing_currency", "pricing_currency")

focus_cost_records = Table(
    "focus_cost_records", Base.metadata,
    Column("id", Uuid, primary_key=True), Column("tenant_id", Uuid, nullable=False),
    Column("ingestion_run_id", Uuid, nullable=False), Column("raw_file_id", Uuid, nullable=False),
    Column("row_number", Integer, nullable=False),
    *[Column(c, _AMT) for c in AMOUNT_COLUMNS],
    *[Column(c, _TS) for c in TIMESTAMP_COLUMNS],
    *[Column(c, Text) for c in TEXT_COLUMNS],
    *[Column(c, JSONB) for c in JSON_COLUMNS],
    *[Column(c, String(16)) for c in SHORT_COLUMNS],
    Column("extensions", JSONB, nullable=False), Column("basis", String(16), nullable=False),
    Column("finality", String(12), nullable=False), Column("source_focus_version", String(16), nullable=False),
    Column("mapper_version", String(32), nullable=False),
)  # fmt: skip

focus_supersessions = Table(
    "focus_supersessions", Base.metadata,
    Column("tenant_id", Uuid, primary_key=True), Column("record_id", Uuid, primary_key=True),
    Column("superseded_by_run_id", Uuid, nullable=False),
)  # fmt: skip
