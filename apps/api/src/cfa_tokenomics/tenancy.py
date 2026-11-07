"""Tenant-scoped database sessions and the row-level-security guard.

Isolation is enforced by PostgreSQL (migration 0005), not by application filters. A session
carries a tenant id into every transaction as the local setting ``app.tenant_id``. No tenant id
means no rows are visible or writable (fail closed).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable

from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

LEGACY_TABLES = (
    "account_grants", "audit_events", "collection_checkpoints", "role_assignments",
    "usage_aggregate_observations", "usage_request_observations",
)  # fmt: skip
MUTABLE_TABLES = (
    "tenants", "business_units", "customers", "environments", "applications", "workloads",
    "application_customers", "price_books", "price_entries", "scenarios", "scenario_drivers",
    "connectors", "ingestion_runs",
)  # fmt: skip
APPEND_ONLY_TABLES = (
    "value_assumptions", "calculation_nodes", "calculation_edges", "raw_files", "ingestion_rejects",
    "focus_cost_records", "focus_supersessions",
)  # fmt: skip
_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def tenant_session(
    engine: Engine,
    tenant_id: uuid.UUID | None,
    setup: Callable[[Connection], None] | None = None,
) -> Session:
    """A session whose every transaction runs under ``tenant_id``.

    ``setup`` runs first in each transaction (used by tests to assume a restricted role)."""
    session = Session(engine, expire_on_commit=False)

    @event.listens_for(session, "after_begin")
    def _bind(_session: Session, _txn: object, connection: Connection) -> None:
        if setup is not None:
            setup(connection)
        connection.execute(
            text("select set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_id) if tenant_id else ""},
        )

    return session


def role_can_bypass_rls(conn: Connection) -> bool:
    """True if the connected role ignores row-level security (superuser or BYPASSRLS)."""
    row = conn.execute(
        text("select rolsuper or rolbypassrls from pg_roles where rolname = current_user")
    ).scalar()
    return bool(row)


def app_role_grants_sql(role: str) -> str:
    """SQL granting a restricted runtime role what it needs. Run it as the database owner.

    The role must be created without SUPERUSER and without BYPASSRLS. Append-only tables get
    SELECT and INSERT only. The legacy usage tables are not yet tenant-isolated (no tenant_id)."""
    if not _ROLE.match(role):
        raise ValueError("role must be lowercase letters, digits and underscores")
    dml = ", ".join((*LEGACY_TABLES, *MUTABLE_TABLES))
    return "\n".join(
        [
            f"GRANT USAGE ON SCHEMA public TO {role};",
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {dml} TO {role};",
            f"GRANT SELECT, INSERT ON {', '.join(APPEND_ONLY_TABLES)} TO {role};",
            f"GRANT SELECT ON alembic_version TO {role};",
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role};",
        ]
    )
