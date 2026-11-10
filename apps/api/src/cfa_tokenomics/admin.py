"""Operator commands. Run against the database as its owner (CFA_DATABASE_URL).

python -m cfa_tokenomics.admin create-tenant NAME CURRENCY
python -m cfa_tokenomics.admin app-role-sql ROLE     prints the grants for the runtime role
python -m cfa_tokenomics.admin assign-legacy-tenant TENANT_ID   rows that predate tenancy
python -m cfa_tokenomics.admin project-usage TENANT_ID   build usage facts from the ledger
"""

import os
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import create_engine

from .alloc.runner import allocation_summary, run_allocation
from .focus.importer import get_or_create_manual_connector, import_focus_file
from .legacy_tenancy import assign_legacy_tenant
from .store import create_tenant
from .tenancy import app_role_grants_sql, tenant_session
from .usage.facts import project_usage


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "create-tenant":
        url = os.environ.get("CFA_DATABASE_URL")
        if not url:
            print("CFA_DATABASE_URL is required", file=sys.stderr)
            return 2
        print(create_tenant(create_engine(url), argv[1], argv[2]))
        return 0
    if len(argv) == 2 and argv[0] == "assign-legacy-tenant":
        return _assign_legacy(argv[1])
    if len(argv) == 2 and argv[0] == "project-usage":
        return _project_usage(argv[1])
    if len(argv) == 4 and argv[0] == "allocate":
        return _allocate(argv[1:])
    if len(argv) >= 3 and argv[0] == "import-focus":
        return _import_focus(argv[1:])
    if len(argv) == 2 and argv[0] == "app-role-sql":
        print(app_role_grants_sql(argv[1]))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


def _assign_legacy(tenant: str) -> int:
    url = os.environ.get("CFA_DATABASE_URL")
    if not url:
        print("CFA_DATABASE_URL is required", file=sys.stderr)
        return 2
    try:
        done = assign_legacy_tenant(create_engine(url), uuid.UUID(tenant))
    except (ValueError, RuntimeError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    if not done:
        print("nothing to assign: every legacy table already has a tenant")
    for table, n in done.items():
        print(f"{table}: {n} row(s) assigned")
    return 0


def _project_usage(tenant: str) -> int:
    url = os.environ.get("CFA_DATABASE_URL")
    if not url:
        print("CFA_DATABASE_URL is required", file=sys.stderr)
        return 2
    tenant_id = uuid.UUID(tenant)
    with tenant_session(create_engine(url), tenant_id) as db:
        res = project_usage(db)
    print(
        f"requests: {res.request_facts} facts from {res.request_rows} rows; "
        f"aggregates: {res.aggregate_inserted} new, {res.aggregate_revised} revised, "
        f"{res.aggregate_unchanged} unchanged"
    )
    return 0


def _allocate(args: list[str]) -> int:
    url = os.environ.get("CFA_DATABASE_URL")
    if not url:
        print("CFA_DATABASE_URL is required", file=sys.stderr)
        return 2
    tenant_id = uuid.UUID(args[0])
    start, end = (datetime.fromisoformat(a).replace(tzinfo=UTC) for a in args[1:3])
    with tenant_session(create_engine(url), tenant_id) as db:
        res = run_allocation(db, tenant_id, start, end, created_by="cli")
        detail = f"lines={res.lines} slices={res.slices} run={res.run_id} {res.error or ''}"
        print(f"{res.status}: {detail}".strip())
        for s in allocation_summary(db):
            cov = "n/a" if s.coverage is None else f"{s.coverage:.1%}"
            print(
                f"{s.currency}: effective total={s.total_effective} "
                f"allocated={s.allocated_effective} unallocated={s.unallocated_effective} "
                f"not_yet_allocated={s.not_yet_allocated_effective} coverage={cov} "
                f"provider_split_lines={s.provider_split_lines}"
            )
    return 0 if res.status in ("succeeded", "unchanged") else 1


def _import_focus(args: list[str]) -> int:
    url = os.environ.get("CFA_DATABASE_URL")
    if not url:
        print("CFA_DATABASE_URL is required", file=sys.stderr)
        return 2
    tenant_id, path = uuid.UUID(args[0]), args[1]
    version = args[args.index("--version") + 1] if "--version" in args else "unknown"
    with open(path, "rb") as fh:
        content = fh.read()
    with tenant_session(create_engine(url), tenant_id) as db:
        cid = get_or_create_manual_connector(db, tenant_id)
        res = import_focus_file(
            db, tenant_id, cid, os.path.basename(path), content, declared_version=version,
            finality="final" if "--final" in args else None,
            allow_partial="--allow-partial" in args,
        )  # fmt: skip
    print(
        f"{res.status}: imported={res.rows_imported} rejected={res.rows_rejected} "
        f"superseded={res.superseded} run={res.run_id} {res.error or ''}".strip()
    )
    return 0 if res.status in ("succeeded", "partial", "duplicate") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
