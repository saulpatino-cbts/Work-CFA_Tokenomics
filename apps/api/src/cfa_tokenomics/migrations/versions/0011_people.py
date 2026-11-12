"""people: the directory mapping behind person pseudonyms, and the display setting

Usage data holds only keyed pseudonyms (ADR 0012, 0013). ``people`` is the one place a pseudonym
maps to a display name, so an administrator can choose to show names. It holds a name and nothing
else: no email, no directory id. ``tenants.person_display`` decides what is shown: ``pseudonym``
(the default) or ``name``. Showing names never copies a name into the cost or usage data.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"

TENANT = "nullif(current_setting('app.tenant_id', true), '')::uuid"
_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("person_display", sa.String(12), nullable=False, server_default="pseudonym"),
    )
    op.create_check_constraint(
        "ck_tenant_person_display", "tenants", "person_display in ('pseudonym','name')"
    )
    op.create_table(
        "people",
        sa.Column("tenant_id", sa.Uuid, primary_key=True),
        sa.Column("pseudonym", sa.String(34), primary_key=True),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_people_tenant"),
        sa.CheckConstraint("source in ('manual','entra','google')", name="ck_people_source"),
        sa.CheckConstraint(
            "pseudonym like 'u\\_%' and char_length(pseudonym) = 34", name="ck_people_pseudonym"
        ),
    )
    op.execute("ALTER TABLE people ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE people FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON people FOR ALL "
        f"USING (tenant_id = {TENANT}) WITH CHECK (tenant_id = {TENANT})"
    )


def downgrade() -> None:
    op.drop_table("people")
    op.drop_constraint("ck_tenant_person_display", "tenants", type_="check")
    op.drop_column("tenants", "person_display")
