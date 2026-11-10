"""normalized usage facts

One row per measurement: a token category from one request, or from one provider window. Quantities
are exact decimals, units and basis are explicit, and every row points back at the ledger row it came
from, so the ledger stays the record and the facts can be rebuilt. Unknown categories produce no row
(unknown is not zero). Sources are never added: source_type is a column, not a roll-up.

Tenant isolation is forced, as on every other tenant table. Rows are revised in place when a
provider revises a window (revision counts it); requests are immutable.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"

TENANT = "nullif(current_setting('app.tenant_id', true), '')::uuid"
_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "usage_facts",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("tenant_id", sa.Uuid, nullable=False),
        sa.Column("grain", sa.String(8), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("account", sa.String(256), nullable=False),
        sa.Column("model_id", sa.String(256), nullable=False),
        sa.Column("sku", sa.String(24), nullable=False),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("measure", sa.String(16), nullable=False),
        sa.Column("statistic", sa.String(16)),
        sa.Column("quantity", sa.Numeric, nullable=False),
        sa.Column("unit", sa.String(16), nullable=False, server_default="tokens"),
        sa.Column("period_start", _TS, nullable=False),
        sa.Column("period_end", _TS, nullable=False),
        sa.Column("basis", sa.String(16), nullable=False),
        sa.Column("quality", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("normalization_version", sa.String(32), nullable=False),
        sa.Column("source_table", sa.String(32), nullable=False),
        sa.Column("source_id", sa.BigInteger, nullable=False),
        sa.Column("projected_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "id", name="uq_usage_facts_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "source_table", "source_id", "measure", name="uq_usage_facts_source"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_usage_facts_tenant"),
        sa.CheckConstraint("grain in ('request','window')", name="ck_fact_grain"),
        sa.CheckConstraint(
            "measure in ('input','output','cache_read','cache_write','reasoning','total')",
            name="ck_fact_measure",
        ),
        sa.CheckConstraint(
            "sku in ('api_on_demand','api_provisioned','subscription','unknown')",
            name="ck_fact_sku",
        ),
        sa.CheckConstraint(
            "source_type in ('cloud_telemetry','vendor_admin_api','app_routed')",
            name="ck_fact_source",
        ),
        sa.CheckConstraint("basis in ('observed','estimated','assumed')", name="ck_fact_basis"),
        sa.CheckConstraint("quantity >= 0", name="ck_fact_quantity"),
        sa.CheckConstraint("period_end >= period_start", name="ck_fact_period"),
        sa.CheckConstraint(
            "(grain = 'window') = (statistic is not null)", name="ck_fact_statistic"
        ),
        sa.CheckConstraint(
            "source_table in ('usage_request_observations','usage_aggregate_observations')",
            name="ck_fact_source_table",
        ),
    )
    op.create_index(
        "ix_usage_facts_scope", "usage_facts", ["tenant_id", "provider", "account", "period_start"]
    )
    op.execute("ALTER TABLE usage_facts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE usage_facts FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON usage_facts FOR ALL "
        f"USING (tenant_id = {TENANT}) WITH CHECK (tenant_id = {TENANT})"
    )


def downgrade() -> None:
    op.drop_table("usage_facts")
