"""FOCUS cost layer: connectors, ingestion runs, raw files, rejects, cost records, supersessions

Cost records, raw files, rejects and supersessions are append-only. A revised export does not edit
earlier rows: it adds rows and a supersession per replaced record, so history stays and "current cost"
is the set of records with no supersession. All tables are tenant-isolated like migration 0005.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"

TENANT = "nullif(current_setting('app.tenant_id', true), '')::uuid"
_TS = sa.DateTime(timezone=True)
_AMT = sa.Numeric(38, 18)


def _tid() -> sa.Column:
    return sa.Column("tenant_id", sa.Uuid, nullable=False)


def upgrade() -> None:
    op.create_table(
        "connectors",
        sa.Column("id", sa.Uuid, primary_key=True),
        _tid(),
        sa.Column("provider_key", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("credential_ref", sa.String(512)),  # a secret-store reference, never a secret
        sa.Column("scope", JSONB, nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_connectors_tenant_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_connectors_name"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_connectors_tenant"),
        sa.CheckConstraint("kind in ('manual_import','api')", name="ck_connector_kind"),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Uuid, primary_key=True),
        _tid(),
        sa.Column("connector_id", sa.Uuid, nullable=False),
        sa.Column("source_name", sa.Text, nullable=False),
        sa.Column("declared_version", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("started_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", _TS),
        sa.Column("row_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("mapper_version", sa.String(32), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("finality", sa.String(12), nullable=False),
        sa.Column("error", sa.Text),
        sa.UniqueConstraint("tenant_id", "id", name="uq_runs_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "connector_id"],
            ["connectors.tenant_id", "connectors.id"],
            name="fk_run_connector",
        ),
        sa.CheckConstraint(
            "status in ('running','succeeded','partial','failed')", name="ck_run_status"
        ),
        sa.CheckConstraint("finality in ('provisional','final')", name="ck_run_finality"),
    )
    # The same file is imported once per connector; a failed attempt may be retried.
    op.create_index(
        "uq_run_file_once", "ingestion_runs", ["tenant_id", "connector_id", "content_hash"],
        unique=True, postgresql_where=sa.text("status in ('running','succeeded','partial')"),
    )  # fmt: skip
    op.create_table(
        "raw_files",
        sa.Column("id", sa.Uuid, primary_key=True),
        _tid(),
        sa.Column("ingestion_run_id", sa.Uuid, nullable=False),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("content_gzip", sa.LargeBinary, nullable=False),
        sa.Column("received_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_raw_files_tenant_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "ingestion_run_id"],
            ["ingestion_runs.tenant_id", "ingestion_runs.id"],
            name="fk_raw_run",
        ),
    )
    op.create_table(
        "ingestion_rejects",
        sa.Column("id", sa.Uuid, primary_key=True),
        _tid(),
        sa.Column("ingestion_run_id", sa.Uuid, nullable=False),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("column_name", sa.String(128)),
        sa.ForeignKeyConstraint(
            ["tenant_id", "ingestion_run_id"],
            ["ingestion_runs.tenant_id", "ingestion_runs.id"],
            name="fk_reject_run",
        ),
    )
    cols = [
        sa.Column("id", sa.Uuid, primary_key=True),
        _tid(),
        sa.Column("ingestion_run_id", sa.Uuid, nullable=False),
        sa.Column("raw_file_id", sa.Uuid, nullable=False),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("billed_cost", _AMT, nullable=False),
        sa.Column("effective_cost", _AMT, nullable=False),
        sa.Column("list_cost", _AMT, nullable=False),
        sa.Column("contracted_cost", _AMT, nullable=False),
        sa.Column("charge_category", sa.String(16), nullable=False),
        sa.Column("charge_period_start", _TS, nullable=False),
        sa.Column("charge_period_end", _TS, nullable=False),
        sa.Column("billing_currency", sa.String(3), nullable=False),
        sa.Column("pricing_currency", sa.String(3)),
        sa.Column("billing_period_start", _TS),
        sa.Column("billing_period_end", _TS),
        sa.Column("list_unit_price", _AMT),
        sa.Column("contracted_unit_price", _AMT),
        sa.Column("consumed_quantity", _AMT),
        sa.Column("pricing_quantity", _AMT),
        sa.Column("commitment_discount_quantity", _AMT),
        sa.Column("tags", JSONB),
        sa.Column("sku_price_details", JSONB),
    ]
    text_cols = [
        "billing_account_id", "billing_account_name", "sub_account_id", "sub_account_name",
        "charge_class", "charge_description", "charge_frequency", "pricing_category",
        "consumed_unit", "pricing_unit", "service_name", "service_category", "service_subcategory",
        "service_provider_name", "host_provider_name", "invoice_issuer_name", "invoice_id",
        "resource_id", "resource_name", "resource_type", "region_id", "region_name",
        "availability_zone", "sku_id", "sku_price_id", "sku_meter", "commitment_discount_id",
        "commitment_discount_name", "commitment_discount_category", "commitment_discount_type",
        "commitment_discount_status", "commitment_discount_unit",
    ]  # fmt: skip
    cols += [sa.Column(c, sa.Text) for c in text_cols]
    cols += [
        sa.Column("extensions", JSONB, nullable=False, server_default="{}"),
        sa.Column("basis", sa.String(16), nullable=False, server_default="observed"),
        sa.Column("finality", sa.String(12), nullable=False),
        sa.Column("source_focus_version", sa.String(16), nullable=False),
        sa.Column("mapper_version", sa.String(32), nullable=False),
    ]
    op.create_table(
        "focus_cost_records", *cols,
        sa.UniqueConstraint("tenant_id", "id", name="uq_focus_tenant_id"),
        sa.ForeignKeyConstraint(["tenant_id", "ingestion_run_id"], ["ingestion_runs.tenant_id", "ingestion_runs.id"], name="fk_focus_run"),
        sa.ForeignKeyConstraint(["tenant_id", "raw_file_id"], ["raw_files.tenant_id", "raw_files.id"], name="fk_focus_raw"),
        sa.CheckConstraint("charge_category in ('Usage','Purchase','Tax','Credit','Adjustment')", name="ck_focus_category"),
        sa.CheckConstraint("charge_period_end > charge_period_start", name="ck_focus_period"),
        sa.CheckConstraint("basis in ('observed','estimated','assumed')", name="ck_focus_basis"),
        sa.CheckConstraint("finality in ('provisional','final')", name="ck_focus_finality"),
        sa.CheckConstraint("char_length(billing_currency) = 3", name="ck_focus_currency"),
    )  # fmt: skip
    op.create_index("ix_focus_period", "focus_cost_records", ["tenant_id", "charge_period_start"])
    op.create_index(
        "ix_focus_scope",
        "focus_cost_records",
        ["tenant_id", "billing_account_id", "sub_account_id"],
    )
    op.create_index("ix_focus_run", "focus_cost_records", ["tenant_id", "ingestion_run_id"])
    op.create_table(
        "focus_supersessions",
        _tid(),
        sa.Column("record_id", sa.Uuid, nullable=False),
        sa.Column("superseded_by_run_id", sa.Uuid, nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "record_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "record_id"],
            ["focus_cost_records.tenant_id", "focus_cost_records.id"],
            name="fk_super_record",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "superseded_by_run_id"],
            ["ingestion_runs.tenant_id", "ingestion_runs.id"],
            name="fk_super_run",
        ),
    )

    for table, append_only in [
        ("connectors", False), ("ingestion_runs", False), ("raw_files", True),
        ("ingestion_rejects", True), ("focus_cost_records", True), ("focus_supersessions", True),
    ]:  # fmt: skip
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        if append_only:
            op.execute(
                f"CREATE POLICY tenant_select ON {table} FOR SELECT USING (tenant_id = {TENANT})"
            )
            op.execute(
                f"CREATE POLICY tenant_insert ON {table} FOR INSERT WITH CHECK (tenant_id = {TENANT})"
            )
        else:
            op.execute(
                f"CREATE POLICY tenant_isolation ON {table} FOR ALL "
                f"USING (tenant_id = {TENANT}) WITH CHECK (tenant_id = {TENANT})"
            )


def downgrade() -> None:
    for table in (
        "focus_supersessions", "focus_cost_records", "ingestion_rejects", "raw_files",
        "ingestion_runs", "connectors",
    ):  # fmt: skip
        op.drop_table(table)
