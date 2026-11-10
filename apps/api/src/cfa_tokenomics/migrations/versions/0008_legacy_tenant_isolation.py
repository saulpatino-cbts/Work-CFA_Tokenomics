"""tenant isolation for the legacy tables

Adds tenant_id and forced row-level security to role_assignments, account_grants, audit_events,
usage_request_observations, usage_aggregate_observations and collection_checkpoints. tenant_id
defaults to the transaction's tenant, so writes made inside a tenant session need no code change
and a write with no tenant fails closed. The audit log becomes append-only.

Rows that already exist have no tenant and nothing guesses one: they stay invisible to every tenant
session until an operator runs ``python -m cfa_tokenomics.admin assign-legacy-tenant TENANT_ID``,
which assigns them and finalizes (NOT NULL, foreign key, tenant-scoped keys). A database with no
rows is finalized here. Until finalized, /readyz reports the install as not ready.

Downgrade restores the global keys and drops tenant_id. It fails if two tenants hold rows that
collide under the global keys, rather than merging data.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

from cfa_tokenomics import legacy_tenancy as lt

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    conn = op.get_bind()
    for t in lt.TABLES:
        op.add_column(t, sa.Column("tenant_id", sa.Uuid, nullable=True))
        op.execute(f"ALTER TABLE {t} ALTER COLUMN tenant_id SET DEFAULT {lt.TENANT}")
    for t, (name, cols) in lt.NEW_KEY.items():
        op.create_index(name, t, list(cols), unique=True)
    op.create_index("ix_audit_tenant_at", "audit_events", ["tenant_id", "at"])
    for t in lt.TABLES:
        lt.install_policies(conn, t)
    if not lt.has_rows(conn):
        lt.finalize(conn)


def downgrade() -> None:
    conn = op.get_bind()
    for t in lt.TABLES:
        op.execute(f"DROP POLICY IF EXISTS legacy_orphans ON {t}")
        for p in ("tenant_isolation", "tenant_select", "tenant_insert"):
            op.execute(f"DROP POLICY IF EXISTS {p} ON {t}")
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_audit_tenant_at", table_name="audit_events")
    # Restore the global keys. A collision means two tenants share a key; stop rather than merge.
    for t, (kind, _name) in lt._OLD_KEY.items():
        if lt.is_finalized(conn, t):
            if kind == "pkey":
                op.execute(f"ALTER TABLE {t} DROP CONSTRAINT {t}_pkey")
        else:
            op.execute(f"DROP INDEX IF EXISTS {lt.NEW_KEY[t][0]}")
    for t, (kind, name) in lt._OLD_KEY.items():
        cols = [c for c in lt.NEW_KEY[t][1] if c != "tenant_id"]
        if kind == "pkey":
            if not _has_pk(conn, t):
                op.create_primary_key(f"{t}_pkey", t, cols)
        elif not _has_constraint(conn, name):
            op.create_unique_constraint(name, t, cols)
    for t in lt.TABLES:
        op.execute(f"ALTER TABLE {t} DROP CONSTRAINT IF EXISTS fk_{t}_tenant")
    for name, _cols in lt.NEW_KEY.values():
        op.execute(f"DROP INDEX IF EXISTS {name}")
    for t in lt.TABLES:
        op.drop_column(t, "tenant_id")


def _has_pk(conn, table: str) -> bool:
    return sa.inspect(conn).get_pk_constraint(table).get("constrained_columns") not in (None, [])


def _has_constraint(conn, name: str) -> bool:
    return bool(
        conn.execute(
            sa.text("select 1 from pg_constraint where conname = :n"), {"n": name}
        ).scalar()
    )
