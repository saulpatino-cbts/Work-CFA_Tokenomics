"""role assignments and audit events

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "role_assignments",
        sa.Column("issuer", sa.String(512), primary_key=True),
        sa.Column("subject", sa.String(512), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(1100), nullable=False),
        sa.CheckConstraint("role in ('admin','user','reader')", name="ck_role_valid"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(1100), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target", sa.String(1100), nullable=False),
        sa.Column("detail", sa.JSON, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("role_assignments")
