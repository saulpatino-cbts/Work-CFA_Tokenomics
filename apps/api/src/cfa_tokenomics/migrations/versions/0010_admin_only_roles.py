"""admin-only roles: admin and finance_viewer

The product is for administrators only (ADR 0013). The end-user and reader roles go away.
Existing assignments become finance_viewer, the read-only role: nobody gains access and nobody
keeps write access they should not have. An administrator can promote them afterwards.

Revision ID: 0010
Revises: 0009
"""

from alembic import op

revision = "0010"
down_revision = "0009"


def upgrade() -> None:
    op.drop_constraint("ck_role_valid", "role_assignments", type_="check")
    op.execute(
        "update role_assignments set role = 'finance_viewer' where role in ('user','reader')"
    )
    op.create_check_constraint(
        "ck_role_valid", "role_assignments", "role in ('admin','finance_viewer')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_role_valid", "role_assignments", type_="check")
    op.execute("update role_assignments set role = 'reader' where role = 'finance_viewer'")
    op.create_check_constraint(
        "ck_role_valid", "role_assignments", "role in ('admin','user','reader')"
    )
