"""usage ledger: request observations, aggregate observations, checkpoints

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"

_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "usage_request_observations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_key", sa.String(1300), nullable=False, unique=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("account", sa.String(256), nullable=False),
        sa.Column("model_id", sa.String(256), nullable=False),
        sa.Column("occurred_at", _TS, nullable=False),
        sa.Column("input_tokens", sa.BigInteger),
        sa.Column("output_tokens", sa.BigInteger),
        sa.Column("cache_read_tokens", sa.BigInteger),
        sa.Column("cache_write_tokens", sa.BigInteger),
        sa.Column("reasoning_tokens", sa.BigInteger),
        sa.Column("provider_total", sa.BigInteger),
        sa.Column("quality", sa.String(16), nullable=False),
        sa.Column("normalization_version", sa.String(32), nullable=False),
        sa.Column("usage_metadata", sa.JSON, nullable=False),
        sa.Column("ingested_at", _TS, nullable=False),
        sa.CheckConstraint(
            "coalesce(input_tokens,0) >= 0 and coalesce(output_tokens,0) >= 0 "
            "and coalesce(cache_read_tokens,0) >= 0 and coalesce(cache_write_tokens,0) >= 0 "
            "and coalesce(reasoning_tokens,0) >= 0 and coalesce(provider_total,0) >= 0",
            name="ck_request_tokens_nonnegative",
        ),
    )
    op.create_index(
        "ix_request_scope_time",
        "usage_request_observations",
        ["provider", "account", "model_id", "occurred_at"],
    )
    op.create_table(
        "usage_aggregate_observations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("account", sa.String(256), nullable=False),
        sa.Column("model_id", sa.String(256), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("window_start", _TS, nullable=False),
        sa.Column("window_end", _TS, nullable=False),
        sa.Column("statistic", sa.String(16), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("quality", sa.String(16), nullable=False),
        sa.Column("normalization_version", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("updated_at", _TS, nullable=False),
        sa.UniqueConstraint(
            "provider", "account", "model_id", "category", "window_start", "window_end", "statistic"
        ),
        sa.CheckConstraint("value >= 0", name="ck_aggregate_nonnegative"),
        sa.CheckConstraint("window_end > window_start", name="ck_aggregate_window"),
    )
    op.create_table(
        "collection_checkpoints",
        sa.Column("provider", sa.String(32), primary_key=True),
        sa.Column("account", sa.String(256), primary_key=True),
        sa.Column("cursor", sa.String(2048)),
        sa.Column("updated_at", _TS, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("collection_checkpoints")
    op.drop_table("usage_aggregate_observations")
    op.drop_index("ix_request_scope_time", table_name="usage_request_observations")
    op.drop_table("usage_request_observations")
