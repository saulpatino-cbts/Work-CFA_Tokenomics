"""sku and source_type dimensions on observations

Existing rows get sku 'unknown' (never guessed). The aggregate natural key now includes sku and
source_type so the same window from two sources is kept as two rows, never merged.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"

_OLD = ["provider", "account", "model_id", "category", "window_start", "window_end", "statistic"]
_NEW = [
    "provider", "account", "model_id", "sku", "source_type",
    "category", "window_start", "window_end", "statistic",
]  # fmt: skip


def _unique_name(cols: list[str]) -> str:
    for uc in sa.inspect(op.get_bind()).get_unique_constraints("usage_aggregate_observations"):
        if list(uc["column_names"]) == cols:
            return uc["name"]
    raise RuntimeError("expected unique constraint not found")


def upgrade() -> None:
    op.add_column(
        "usage_request_observations",
        sa.Column("sku", sa.String(24), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "usage_request_observations",
        sa.Column("source_type", sa.String(24), nullable=False, server_default="app_routed"),
    )
    op.add_column(
        "usage_aggregate_observations",
        sa.Column("sku", sa.String(24), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "usage_aggregate_observations",
        sa.Column("source_type", sa.String(24), nullable=False, server_default="cloud_telemetry"),
    )
    op.drop_constraint(_unique_name(_OLD), "usage_aggregate_observations", type_="unique")
    op.create_unique_constraint("uq_aggregate_natural_key", "usage_aggregate_observations", _NEW)
    for t in ("usage_request_observations", "usage_aggregate_observations"):
        op.create_check_constraint(
            f"ck_{t}_sku", t, "sku in ('api_on_demand','api_provisioned','subscription','unknown')"
        )
        op.create_check_constraint(
            f"ck_{t}_source",
            t,
            "source_type in ('cloud_telemetry','vendor_admin_api','app_routed')",
        )


def downgrade() -> None:
    """Fails if rows now differ only by sku/source_type; resolve those before downgrading."""
    for t in ("usage_request_observations", "usage_aggregate_observations"):
        op.drop_constraint(f"ck_{t}_source", t, type_="check")
        op.drop_constraint(f"ck_{t}_sku", t, type_="check")
    op.drop_constraint("uq_aggregate_natural_key", "usage_aggregate_observations", type_="unique")
    op.create_unique_constraint(None, "usage_aggregate_observations", _OLD)
    for t in ("usage_aggregate_observations", "usage_request_observations"):
        op.drop_column(t, "source_type")
        op.drop_column(t, "sku")
