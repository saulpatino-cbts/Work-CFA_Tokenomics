"""economics core: tenancy, applications, price books, assumptions, scenarios, calculation nodes

Every table carries tenant_id and has row-level security forced on, keyed to the transaction-local
setting ``app.tenant_id``. No setting means no rows (fail closed). Foreign keys include tenant_id, so a
record cannot reference another tenant's row even through a privileged write. value_assumptions,
calculation_nodes and calculation_edges are append-only: they get SELECT and INSERT policies only.

The runtime must connect as a role that is not a superuser and does not have BYPASSRLS, because those
roles ignore row-level security. The API refuses readiness otherwise.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"

TENANT = "nullif(current_setting('app.tenant_id', true), '')::uuid"
_TS = sa.DateTime(timezone=True)
_MONEY = sa.Numeric(28, 10)
_QTY = sa.Numeric(38, 12)
_BASIS = "('observed','estimated','assumed')"

# (table, tenant column, append_only)
RLS_TABLES = [
    ("tenants", "id", False),
    ("business_units", "tenant_id", False),
    ("customers", "tenant_id", False),
    ("environments", "tenant_id", False),
    ("applications", "tenant_id", False),
    ("workloads", "tenant_id", False),
    ("application_customers", "tenant_id", False),
    ("price_books", "tenant_id", False),
    ("price_entries", "tenant_id", False),
    ("value_assumptions", "tenant_id", True),
    ("scenarios", "tenant_id", False),
    ("scenario_drivers", "tenant_id", False),
    ("calculation_nodes", "tenant_id", True),
    ("calculation_edges", "tenant_id", True),
]


def _tid() -> sa.Column:
    return sa.Column("tenant_id", sa.Uuid, nullable=False)


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("base_currency", sa.String(3), nullable=False),
        sa.Column("fiscal_year_start_month", sa.SmallInteger, nullable=False, server_default="1"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("char_length(base_currency) = 3", name="ck_tenant_currency"),
        sa.CheckConstraint("fiscal_year_start_month between 1 and 12", name="ck_tenant_fiscal"),
    )

    def owned(name: str, *cols, **kw):
        op.create_table(
            name,
            sa.Column("id", sa.Uuid, primary_key=True),
            _tid(),
            *cols,
            sa.UniqueConstraint("tenant_id", "id", name=f"uq_{name}_tenant_id"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=f"fk_{name}_tenant"),
            **kw,
        )

    owned(
        "business_units",
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("parent_id", sa.Uuid),
        sa.Column("cost_center", sa.String(128)),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_business_units_name"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["business_units.tenant_id", "business_units.id"],
            name="fk_bu_parent",
        ),
    )
    owned(
        "customers",
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("segment", sa.String(128)),
        sa.Column("external_ref", sa.String(256)),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_customers_name"),
    )
    owned(
        "environments",
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_environments_name"),
        sa.CheckConstraint("kind in ('prod','test','dev','other')", name="ck_environment_kind"),
    )
    owned(
        "applications",
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("business_unit_id", sa.Uuid),
        sa.Column("owner", sa.String(256)),
        sa.Column("lifecycle", sa.String(8), nullable=False, server_default="run"),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("initial_investment", _MONEY),
        sa.Column("investment_basis", sa.String(16)),
        sa.Column("amortization_months", sa.Integer),
        sa.Column("description", sa.Text),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_applications_name"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "business_unit_id"],
            ["business_units.tenant_id", "business_units.id"],
            name="fk_app_bu",
        ),
        sa.CheckConstraint("lifecycle in ('build','run','retire')", name="ck_app_lifecycle"),
        sa.CheckConstraint(
            f"investment_basis is null or investment_basis in {_BASIS}", name="ck_app_inv_basis"
        ),
        sa.CheckConstraint(
            "initial_investment is null or initial_investment >= 0", name="ck_app_inv_nonneg"
        ),
        sa.CheckConstraint(
            "amortization_months is null or amortization_months > 0", name="ck_app_amort"
        ),
        sa.CheckConstraint(
            "(initial_investment is null) = (investment_basis is null)", name="ck_app_inv_has_basis"
        ),
    )
    owned(
        "workloads",
        sa.Column("application_id", sa.Uuid, nullable=False),
        sa.Column("environment_id", sa.Uuid, nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "application_id", "environment_id", "name", name="uq_workloads_name"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_workload_app",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "environment_id"],
            ["environments.tenant_id", "environments.id"],
            name="fk_workload_env",
        ),
        sa.CheckConstraint(
            "kind in ('inference','retrieval','batch','agent','ui','other')",
            name="ck_workload_kind",
        ),
    )
    op.create_table(
        "application_customers",
        _tid(),
        sa.Column("application_id", sa.Uuid, nullable=False),
        sa.Column("customer_id", sa.Uuid, nullable=False),
        sa.Column("usage_share", sa.Numeric(9, 8)),
        sa.Column("basis", sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "application_id", "customer_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_appcust_app",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_appcust_cust",
        ),
        sa.CheckConstraint(f"basis in {_BASIS}", name="ck_appcust_basis"),
        sa.CheckConstraint(
            "usage_share is null or (usage_share >= 0 and usage_share <= 1)",
            name="ck_appcust_share",
        ),
    )
    owned(
        "price_books",
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_price_books_name"),
        sa.CheckConstraint(
            "source in ('list','negotiated','observed_derived')", name="ck_pricebook_source"
        ),
    )
    owned(
        "price_entries",
        sa.Column("price_book_id", sa.Uuid, nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model_key", sa.String(256), nullable=False),
        sa.Column("measure", sa.String(32), nullable=False),
        sa.Column("unit_price", _MONEY, nullable=False),
        sa.Column("per_quantity", _QTY, nullable=False, server_default="1000000"),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("effective_from", _TS, nullable=False),
        sa.Column("effective_to", _TS),
        sa.Column("inclusion_rule", sa.String(256)),
        sa.Column("note", sa.Text),
        sa.UniqueConstraint(
            "price_book_id",
            "provider",
            "model_key",
            "measure",
            "effective_from",
            name="uq_price_entry_start",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "price_book_id"],
            ["price_books.tenant_id", "price_books.id"],
            name="fk_price_entry_book",
        ),
        sa.CheckConstraint("unit_price >= 0", name="ck_price_nonneg"),
        sa.CheckConstraint("per_quantity > 0", name="ck_price_per_positive"),
        sa.CheckConstraint(
            "effective_to is null or effective_to > effective_from", name="ck_price_window"
        ),
    )
    op.create_table(
        "value_assumptions",
        sa.Column("id", sa.Uuid, primary_key=True),
        _tid(),
        sa.Column("application_id", sa.Uuid, nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", _QTY),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("basis", sa.String(16), nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("author", sa.String(1100), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "application_id", "key", "version", name="uq_assumption_version"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_assumption_app",
        ),
        sa.CheckConstraint(f"basis in {_BASIS}", name="ck_assumption_basis"),
        sa.CheckConstraint("char_length(btrim(rationale)) > 0", name="ck_assumption_rationale"),
        sa.CheckConstraint("version >= 1", name="ck_assumption_version"),
    )
    owned(
        "scenarios",
        sa.Column("application_id", sa.Uuid, nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("base_scenario_id", sa.Uuid),
        sa.Column("customer_id", sa.Uuid),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "application_id", "name", name="uq_scenarios_name"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "application_id"],
            ["applications.tenant_id", "applications.id"],
            name="fk_scenario_app",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "base_scenario_id"],
            ["scenarios.tenant_id", "scenarios.id"],
            name="fk_scenario_base",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_scenario_customer",
        ),
        sa.CheckConstraint(
            "kind in ('baseline','current','forecast','optimized','customer_proposal')",
            name="ck_scenario_kind",
        ),
        sa.CheckConstraint("status in ('draft','final','archived')", name="ck_scenario_status"),
    )
    owned(
        "scenario_drivers",
        sa.Column("scenario_id", sa.Uuid, nullable=False),
        sa.Column("driver_key", sa.String(128), nullable=False),
        sa.Column("value", _QTY),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("basis", sa.String(16), nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "scenario_id", "driver_key", name="uq_driver_key"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "scenario_id"],
            ["scenarios.tenant_id", "scenarios.id"],
            name="fk_driver_scenario",
        ),
        sa.CheckConstraint(f"basis in {_BASIS}", name="ck_driver_basis"),
    )
    op.create_table(
        "calculation_nodes",
        _tid(),
        sa.Column("id", sa.String(16), nullable=False),
        sa.Column("key", sa.String(256), nullable=False),
        sa.Column("formula_id", sa.String(128), nullable=False),
        sa.Column("formula_version", sa.Integer, nullable=False),
        # Unconstrained numeric: node values are exact (up to 34 digits) and must round-trip, because
        # the node id is a hash of the exact value.
        sa.Column("value", sa.Numeric),
        sa.Column("unit", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(3)),
        sa.Column("mix_observed", sa.Numeric, nullable=False),
        sa.Column("mix_estimated", sa.Numeric, nullable=False),
        sa.Column("mix_assumed", sa.Numeric, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("note", sa.Text, nullable=False, server_default=""),
        sa.Column("label", sa.Text, nullable=False, server_default=""),
        sa.Column("source_ref", sa.String(256)),
        sa.Column("computed_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("tenant_id", "id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_calcnode_tenant"),
        sa.CheckConstraint("(value is null) = (status <> 'ok')", name="ck_calcnode_value_status"),
        sa.CheckConstraint(
            "status in ('ok','unknown','not_reached','infeasible')", name="ck_calcnode_status"
        ),
    )
    op.create_table(
        "calculation_edges",
        _tid(),
        sa.Column("parent_id", sa.String(16), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("child_id", sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "parent_id", "position"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["calculation_nodes.tenant_id", "calculation_nodes.id"],
            name="fk_edge_parent",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "child_id"],
            ["calculation_nodes.tenant_id", "calculation_nodes.id"],
            name="fk_edge_child",
        ),
    )

    for table, col, append_only in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        if append_only:
            op.execute(
                f"CREATE POLICY tenant_select ON {table} FOR SELECT USING ({col} = {TENANT})"
            )
            op.execute(
                f"CREATE POLICY tenant_insert ON {table} FOR INSERT WITH CHECK ({col} = {TENANT})"
            )
        else:
            op.execute(
                f"CREATE POLICY tenant_isolation ON {table} FOR ALL "
                f"USING ({col} = {TENANT}) WITH CHECK ({col} = {TENANT})"
            )


def downgrade() -> None:
    for table in (
        "calculation_edges", "calculation_nodes", "scenario_drivers", "scenarios", "value_assumptions",
        "price_entries", "price_books", "application_customers", "workloads", "applications",
        "environments", "customers", "business_units", "tenants",
    ):  # fmt: skip
        op.drop_table(table)
