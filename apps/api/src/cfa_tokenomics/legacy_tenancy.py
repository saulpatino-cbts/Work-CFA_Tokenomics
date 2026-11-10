"""Tenant isolation for the tables that existed before the tenancy model (Phase 1 slice 7).

Migration 0008 adds ``tenant_id`` and row-level security to the six legacy tables. Rows written
before that have no tenant, and nothing may guess one: they stay invisible to every tenant session
until an operator names the tenant with ``assign-legacy-tenant``. That command assigns the rows and
then *finalizes*: it makes ``tenant_id`` mandatory, adds the foreign key and swaps the old global
keys for tenant-scoped ones. An install with no legacy rows is finalized by the migration itself.

Functions here take a connection and are idempotent, so an interrupted run can simply be repeated.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

TENANT = "nullif(current_setting('app.tenant_id', true), '')::uuid"

TABLES = (
    "usage_request_observations", "usage_aggregate_observations", "collection_checkpoints",
    "role_assignments", "account_grants", "audit_events",
)  # fmt: skip

# Old global key to drop at finalize, and the tenant-scoped replacement (created by the migration).
_AGG_COLS = (
    "provider", "account", "model_id", "sku", "source_type", "category", "window_start",
    "window_end", "statistic",
)  # fmt: skip
_OLD_KEY = {
    "usage_request_observations": ("unique", "usage_request_observations_source_key_key"),
    "usage_aggregate_observations": ("unique", "uq_aggregate_natural_key"),
    "collection_checkpoints": ("pkey", "collection_checkpoints_pkey"),
    "role_assignments": ("pkey", "role_assignments_pkey"),
    "account_grants": ("pkey", "account_grants_pkey"),
}
# table -> (new unique index, its columns). For key-less tables the index becomes the primary key.
NEW_KEY = {
    "usage_request_observations": ("uq_request_tenant_source", ("tenant_id", "source_key")),
    "usage_aggregate_observations": ("uq_aggregate_tenant_natural_key", ("tenant_id", *_AGG_COLS)),
    "collection_checkpoints": ("uq_checkpoint_tenant", ("tenant_id", "provider", "account")),
    "role_assignments": ("uq_role_tenant", ("tenant_id", "issuer", "subject")),
    "account_grants": (
        "uq_grant_tenant", ("tenant_id", "issuer", "subject", "provider", "account"),
    ),
}  # fmt: skip
_IS_OWNER = (
    "pg_has_role(current_user, "
    "(select relowner from pg_class where oid = '{t}'::regclass), 'USAGE')"
)


def is_finalized(conn: Connection, table: str) -> bool:
    nullable = conn.execute(
        text(
            "select is_nullable from information_schema.columns "
            "where table_schema = current_schema() and table_name = :t and column_name = 'tenant_id'"
        ),
        {"t": table},
    ).scalar()
    return nullable == "NO"


def unassigned_tables(conn: Connection) -> list[str]:
    """Tables still waiting for ``assign-legacy-tenant``. Reads metadata only, so it works for the
    runtime role even though row-level security hides the rows themselves."""
    return [t for t in TABLES if not is_finalized(conn, t)]


def install_policies(conn: Connection, table: str) -> None:
    """Forced row-level security. The audit log is append-only: select and insert, nothing else.
    A separate policy lets the table owner (never the runtime role) see and claim unassigned rows."""
    conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
    if table == "audit_events":
        conn.execute(
            text(f"CREATE POLICY tenant_select ON {table} FOR SELECT USING (tenant_id = {TENANT})")
        )
        conn.execute(
            text(
                f"CREATE POLICY tenant_insert ON {table} FOR INSERT WITH CHECK (tenant_id = {TENANT})"
            )
        )
    else:
        conn.execute(
            text(
                f"CREATE POLICY tenant_isolation ON {table} FOR ALL "
                f"USING (tenant_id = {TENANT}) WITH CHECK (tenant_id = {TENANT})"
            )
        )
    owner = _IS_OWNER.format(t=table)
    conn.execute(
        text(
            f"CREATE POLICY legacy_orphans ON {table} FOR ALL "
            f"USING (tenant_id is null and {owner}) "
            f"WITH CHECK (tenant_id is not null and {owner})"
        )
    )


def has_rows(conn: Connection) -> bool:
    return any(conn.execute(text(f"select exists (select 1 from {t})")).scalar() for t in TABLES)


def finalize_table(conn: Connection, table: str) -> None:
    """Make tenant_id mandatory and swap the global key for the tenant-scoped one."""
    if is_finalized(conn, table):
        return
    left = conn.execute(text(f"select count(*) from {table} where tenant_id is null")).scalar()
    if left:
        raise RuntimeError(f"{table} still has {left} row(s) without a tenant")
    conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN tenant_id SET NOT NULL"))
    conn.execute(
        text(
            f"ALTER TABLE {table} ADD CONSTRAINT fk_{table}_tenant "
            "FOREIGN KEY (tenant_id) REFERENCES tenants (id)"
        )
    )
    if table in _OLD_KEY:
        kind, name = _OLD_KEY[table]
        conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT {name}"))
        if kind == "pkey":
            conn.execute(
                text(
                    f"ALTER TABLE {table} ADD CONSTRAINT {table}_pkey "
                    f"PRIMARY KEY USING INDEX {NEW_KEY[table][0]}"
                )
            )
    conn.execute(text(f"DROP POLICY IF EXISTS legacy_orphans ON {table}"))


def finalize(conn: Connection) -> None:
    for t in TABLES:
        finalize_table(conn, t)


def assign_legacy_tenant(engine: Engine, tenant_id: uuid.UUID) -> dict[str, int]:
    """Give every unassigned legacy row to ``tenant_id`` and finalize, in one transaction.

    Run as the table owner. Returns the rows assigned per table. Refuses an unknown tenant. If it
    fails nothing changes, and it is safe to run again."""
    assigned: dict[str, int] = {}
    with engine.begin() as conn:
        conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
        if not conn.execute(
            text("select exists (select 1 from tenants where id = :t)"), {"t": tenant_id}
        ).scalar():
            raise ValueError(f"no such tenant {tenant_id}")
        for t in TABLES:
            if is_finalized(conn, t):
                continue
            res = conn.execute(
                text(f"update {t} set tenant_id = :t where tenant_id is null"), {"t": tenant_id}
            )
            assigned[t] = res.rowcount
        finalize(conn)
    return assigned
