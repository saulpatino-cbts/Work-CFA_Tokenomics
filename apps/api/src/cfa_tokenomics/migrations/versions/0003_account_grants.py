"""per-identity account grants for usage reads

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.create_table(
        "account_grants",
        sa.Column("issuer", sa.String(512), primary_key=True),
        sa.Column("subject", sa.String(512), primary_key=True),
        sa.Column("provider", sa.String(32), primary_key=True),
        sa.Column("account", sa.String(256), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(1100), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("account_grants")
