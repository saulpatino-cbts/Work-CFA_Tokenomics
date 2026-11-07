"""allocation: rules, drivers, runs, allocated slices; FOCUS provider-split columns

Rules, drivers and allocated slices are append-only: a changed rule is a new version, a changed driver is
a new version, and a re-run adds slices rather than editing earlier ones. "Current allocation" for a cost
line is the slices of the latest successful run that included it. Every table is tenant-isolated.

Also adds the FOCUS 1.3 provider-calculated split-allocation columns to focus_cost_records, so provider
split rows are visible and can be flagged instead of silently summed with their origin charges.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"

TENANT = "nullif(current_setting('app.tenant_id', true), '')::uuid"
_TS = sa.DateTime(timezone=True)
_AMT = sa.Numeric(38, 18)
_BASIS = "('observed','estimated','assumed')"


def _tid() -> sa.Column:
    return sa.Column("tenant_id", sa.Uuid, nullable=False)


def upgrade() -> None:
    for col in ("allocated_method_id", "allocated_resource_id", "allocated_resource_name"):
        op.add_column("focus_cost_records", sa.Column(col, sa.Text))
    op.add_column("focus_cost_records", sa.Column("allocated_method_details", JSONB))
    op.add_column("focus_cost_records", sa.Column("allocated_tags", JSONB))

    op.create_table(
        "allocation_rules",
        sa.Column("id", sa.Uuid, primary_key=True),
        _tid(),
        sa.Column("rule_key", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("priority", sa.Integer, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("conditions", JSONB, nullable=False),
        sa.Column("params", JSONB, nullable=False),
        sa.Column("author", sa.String(1100), nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "rule_key", "version", name="uq_rule_version"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_rule_tenant"),
        sa.CheckConstraint(
            "method in ('direct','tag','fixed_percent','even','proportional')",
            name="ck_rule_method",
        ),
        sa.CheckConstraint("version >= 1", name="ck_rule_version"),
    )
    op.create_table(
        "allocation_drivers",
        sa.Column("id", sa.Uuid, primary_key=True),
        _tid(),
        sa.Column("rule_key", sa.String(128), nullable=False),
        sa.Column("application_id", sa.Uuid, nullable=False),
        sa.Column("period_start", _TS, nullable=False),
        sa.Column("period_end", _TS, nullable=False),
        sa.Column("value", sa.Numeric(38, 12), nullable=False),
        sa.Column("basis", sa.String(16), nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("author", sa.String(1100), nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id",
            "rule_key",
            "application_id",
            "period_start",
            "version",
            name="uq_driver_version",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_driver_app",
        ),
        sa.CheckConstraint("value >= 0", name="ck_driver_nonneg"),
        sa.CheckConstraint("period_end > period_start", name="ck_driver_period"),
        sa.CheckConstraint(f"basis in {_BASIS}", name="ck_alloc_driver_basis"),
        sa.CheckConstraint("char_length(btrim(source)) > 0", name="ck_driver_source"),
    )
    op.create_table(
        "allocation_runs",
        sa.Column("id", sa.Uuid, primary_key=True),
        _tid(),
        sa.Column("window_start", _TS, nullable=False),
        sa.Column("window_end", _TS, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("rules_hash", sa.String(64), nullable=False),
        sa.Column("inputs_hash", sa.String(64), nullable=False),
        sa.Column("line_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("slice_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(1100), nullable=False),
        # Strictly increasing order of runs. "Latest run" must never depend on comparing clocks, which tie.
        sa.Column("seq", sa.BigInteger, sa.Identity(always=True), nullable=False),
        sa.Column("started_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", _TS),
        sa.Column("error", sa.Text),
        sa.UniqueConstraint("tenant_id", "id", name="uq_alloc_runs_tenant_id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_alloc_run_tenant"),
        sa.CheckConstraint(
            "status in ('running','succeeded','failed')", name="ck_alloc_run_status"
        ),
        sa.CheckConstraint("window_end > window_start", name="ck_alloc_run_window"),
    )
    op.create_table(
        "allocated_costs",
        sa.Column("id", sa.Uuid, primary_key=True),
        _tid(),
        sa.Column("allocation_run_id", sa.Uuid, nullable=False),
        sa.Column("focus_cost_id", sa.Uuid, nullable=False),
        sa.Column("application_id", sa.Uuid),
        sa.Column("workload_id", sa.Uuid),
        sa.Column("rule_key", sa.String(128)),
        sa.Column("rule_version", sa.Integer),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(64)),
        sa.Column("share", _AMT, nullable=False),
        sa.Column("billed_cost", _AMT, nullable=False),
        sa.Column("effective_cost", _AMT, nullable=False),
        sa.Column("list_cost", _AMT, nullable=False),
        sa.Column("contracted_cost", _AMT, nullable=False),
        sa.Column("billing_currency", sa.String(3), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "allocation_run_id"],
            ["allocation_runs.tenant_id", "allocation_runs.id"],
            name="fk_alloc_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "focus_cost_id"],
            ["focus_cost_records.tenant_id", "focus_cost_records.id"],
            name="fk_alloc_cost",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_alloc_app",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workload_id"],
            ["workloads.tenant_id", "workloads.id"],
            name="fk_alloc_workload",
        ),
        sa.CheckConstraint(
            "method in ('direct','tag','fixed_percent','even','proportional','unallocated')",
            name="ck_alloc_method",
        ),
        sa.CheckConstraint(
            "(application_id is null) = (method = 'unallocated')", name="ck_alloc_unallocated"
        ),
        sa.CheckConstraint("share >= 0 and share <= 1", name="ck_alloc_share"),
    )
    op.create_index("ix_alloc_cost", "allocated_costs", ["tenant_id", "focus_cost_id"])
    op.create_index("ix_alloc_run", "allocated_costs", ["tenant_id", "allocation_run_id"])
    op.create_index("ix_alloc_app", "allocated_costs", ["tenant_id", "application_id"])

    for table, append_only in [
        ("allocation_rules", True), ("allocation_drivers", True), ("allocation_runs", False),
        ("allocated_costs", True),
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
    for table in ("allocated_costs", "allocation_runs", "allocation_drivers", "allocation_rules"):
        op.drop_table(table)
    for col in (
        "allocated_tags",
        "allocated_method_details",
        "allocated_resource_name",
        "allocated_resource_id",
        "allocated_method_id",
    ):
        op.drop_column("focus_cost_records", col)
