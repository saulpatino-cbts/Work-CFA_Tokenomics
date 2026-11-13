"""Import a FOCUS CSV into the cost layer.

Guarantees:
- The same file is imported once per connector.
- Everything for one file happens in one transaction; a failure leaves no partial cost data.
- By default a file with any rejected row is refused as a whole. A partial import silently drops money,
  and a revised export would then supersede good earlier rows. ``allow_partial=True`` is explicit consent.
- A revised export replaces earlier rows only for the (billing account, sub account) pairs it contains,
  and only inside the charge-period window it covers. Replaced rows stay as history (supersession rows);
  nothing is edited or deleted. Overlapping exports are never added together.
- The raw file is kept (gzip) and every record points to its file and row.
"""

from __future__ import annotations

import gzip
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.orm import Session

from . import columns as C
from . import tables as T
from .parse import FileError, ParseResult, parse_focus_csv

CHUNK = 1000


@dataclass
class ImportResult:
    status: str  # succeeded, partial, failed, duplicate
    run_id: uuid.UUID | None = None
    rows_imported: int = 0
    rows_rejected: int = 0
    superseded: int = 0
    reject_reasons: dict[str, int] = field(default_factory=dict)
    unknown_columns: list[str] = field(default_factory=list)
    dropped_identity_columns: list[str] = field(default_factory=list)
    error: str | None = None
    duplicate_of: uuid.UUID | None = None


def get_or_create_manual_connector(
    db: Session, tenant_id: uuid.UUID, name: str = "manual-focus-import"
) -> uuid.UUID:
    found = db.execute(select(T.connectors.c.id).where(T.connectors.c.name == name)).scalar()
    if found:
        return found
    cid = uuid.uuid4()
    db.execute(
        insert(T.connectors).values(
            id=cid,
            tenant_id=tenant_id,
            provider_key="manual",
            kind="manual_import",
            name=name,
            scope={},
            enabled=True,
        )  # fmt: skip
    )
    db.commit()
    return cid


def _finality(rows, now: datetime, final_after_days: int) -> str:
    if not rows:
        return "provisional"
    last = max(r.values["charge_period_end"] for r in rows)
    return "final" if last + timedelta(days=final_after_days) <= now else "provisional"


def _record(r, base: dict) -> dict:
    row = {
        c: None
        for c in (
            *T.AMOUNT_COLUMNS,
            *T.TIMESTAMP_COLUMNS,
            *T.TEXT_COLUMNS,
            *T.JSON_COLUMNS,
            *T.SHORT_COLUMNS,
        )
    }
    row.update(r.values)
    row.update(base, id=uuid.uuid4(), row_number=r.row_number, extensions=r.extensions)
    return row


def import_focus_file(
    db: Session,
    tenant_id: uuid.UUID,
    connector_id: uuid.UUID,
    filename: str,
    content: bytes,
    *,
    declared_version: str = "unknown",
    finality: str | None = None,
    final_after_days: int = 7,
    allow_partial: bool = False,
    keep_identity_columns: bool = False,
    assume_timezone: str | None = "UTC",
    now: datetime | None = None,
    max_bytes: int = 100_000_000,
    basis: str = "observed",
) -> ImportResult:
    if basis not in ("observed", "estimated", "assumed"):
        raise ValueError("basis must be observed, estimated or assumed")
    now = now or datetime.now(UTC)
    digest = hashlib.sha256(content).hexdigest()
    prior = db.execute(
        select(T.ingestion_runs.c.id).where(
            T.ingestion_runs.c.connector_id == connector_id,
            T.ingestion_runs.c.content_hash == digest,
            T.ingestion_runs.c.status.in_(("running", "succeeded", "partial")),
        )
    ).scalar()
    if prior:
        return ImportResult("duplicate", duplicate_of=prior)

    run_id = uuid.uuid4()
    db.execute(
        insert(T.ingestion_runs).values(
            id=run_id,
            tenant_id=tenant_id,
            connector_id=connector_id,
            source_name=filename,
            declared_version=declared_version
            if declared_version in C.DECLARED_VERSIONS
            else "unknown",
            status="running",
            row_count=0,
            rejected_count=0,
            mapper_version=C.MAPPER_VERSION,
            content_hash=digest,
            finality=finality or "provisional",
        )  # fmt: skip
    )
    raw_id = uuid.uuid4()
    if len(content) <= max_bytes:
        db.execute(
            insert(T.raw_files).values(
                id=raw_id,
                tenant_id=tenant_id,
                ingestion_run_id=run_id,
                filename=filename,
                content_hash=digest,
                size_bytes=len(content),
                content_gzip=gzip.compress(content),
            )  # fmt: skip
        )

    def finish(status: str, error: str | None = None, **counts) -> None:
        db.execute(
            update(T.ingestion_runs).where(T.ingestion_runs.c.id == run_id)
            .values(status=status, error=error, finished_at=func.now(), **counts)
        )  # fmt: skip
        db.commit()

    try:
        parsed: ParseResult = parse_focus_csv(
            content,
            declared_version,
            max_bytes,
            keep_identity_columns=keep_identity_columns,
            assume_timezone=assume_timezone,
        )
    except FileError as exc:
        finish("failed", str(exc))
        return ImportResult("failed", run_id, error=str(exc))

    reasons: dict[str, int] = {}
    for rj in parsed.rejects:
        reasons[rj.reason] = reasons.get(rj.reason, 0) + 1
    if parsed.rejects:
        db.execute(
            insert(T.ingestion_rejects),
            [
                {"id": uuid.uuid4(), "tenant_id": tenant_id, "ingestion_run_id": run_id,
                 "row_number": rj.row_number, "reason": rj.reason, "column_name": rj.column}
                for rj in parsed.rejects
            ],
        )  # fmt: skip
    if parsed.rejects and not allow_partial:
        msg = f"{len(parsed.rejects)} rows were rejected; nothing was imported (see ingestion_rejects)"
        finish("failed", msg, rejected_count=len(parsed.rejects))
        return ImportResult("failed", run_id, rows_rejected=len(parsed.rejects), reject_reasons=reasons,
                            unknown_columns=parsed.unknown_columns, error=msg)  # fmt: skip

    fin = finality or _finality(parsed.rows, now, final_after_days)
    base = {
        "tenant_id": tenant_id, "ingestion_run_id": run_id, "raw_file_id": raw_id, "basis": basis,
        "finality": fin, "source_focus_version": declared_version, "mapper_version": C.MAPPER_VERSION,
    }  # fmt: skip
    superseded = 0
    try:
        with db.begin_nested():
            for i in range(0, len(parsed.rows), CHUNK):
                db.execute(
                    insert(T.focus_cost_records),
                    [_record(r, base) for r in parsed.rows[i : i + CHUNK]],
                )
            superseded = _supersede(db, tenant_id, connector_id, run_id, parsed)
        status = "partial" if parsed.rejects else "succeeded"
        finish(
            status,
            None,
            row_count=len(parsed.rows),
            rejected_count=len(parsed.rejects),
            finality=fin,
        )
    except Exception as exc:  # nothing from this file may remain
        db.rollback()
        # The run row and raw file were rolled back with the transaction; record the failure afresh.
        msg = f"import failed: {type(exc).__name__}"
        db.execute(
            insert(T.ingestion_runs).values(
                id=run_id,
                tenant_id=tenant_id,
                connector_id=connector_id,
                source_name=filename,
                declared_version=declared_version
                if declared_version in C.DECLARED_VERSIONS
                else "unknown",
                status="failed",
                row_count=0,
                rejected_count=len(parsed.rejects),
                mapper_version=C.MAPPER_VERSION,
                content_hash=digest,
                finality=fin,
                error=msg,
            )  # fmt: skip
        )
        db.commit()
        return ImportResult("failed", run_id, error=msg)
    return ImportResult(
        status,
        run_id,
        len(parsed.rows),
        len(parsed.rejects),
        superseded,
        reasons,
        parsed.unknown_columns,
        parsed.dropped_identity_columns,
    )


def _supersede(
    db: Session,
    tenant_id: uuid.UUID,
    connector_id: uuid.UUID,
    run_id: uuid.UUID,
    parsed: ParseResult,
) -> int:
    """Supersede earlier current records this file replaces: same connector, same (billing account,
    sub account) pair, charge period starting inside the window this file covers for that pair."""
    windows: dict[tuple[str | None, str | None], list[datetime]] = {}
    for r in parsed.rows:
        key = (r.values.get("billing_account_id"), r.values.get("sub_account_id"))
        lo, hi = windows.setdefault(
            key, [r.values["charge_period_start"], r.values["charge_period_end"]]
        )
        windows[key] = [
            min(lo, r.values["charge_period_start"]),
            max(hi, r.values["charge_period_end"]),
        ]
    total = 0
    for (ba, sa), (lo, hi) in windows.items():
        res = db.execute(
            text(
                "insert into focus_supersessions (tenant_id, record_id, superseded_by_run_id) "
                "select r.tenant_id, r.id, :run from focus_cost_records r "
                "join ingestion_runs ir on ir.tenant_id = r.tenant_id and ir.id = r.ingestion_run_id "
                "where ir.connector_id = :conn and r.ingestion_run_id <> :run "
                "and r.billing_account_id is not distinct from cast(:ba as text) "
                "and r.sub_account_id is not distinct from cast(:sa as text) "
                "and r.charge_period_start >= :lo and r.charge_period_start < :hi "
                "and not exists (select 1 from focus_supersessions s "
                "where s.tenant_id = r.tenant_id and s.record_id = r.id)"
            ),
            {"run": run_id, "conn": connector_id, "ba": ba, "sa": sa, "lo": lo, "hi": hi},
        )
        total += res.rowcount
    return total


def current_cost_summary(db: Session) -> list[dict]:
    """Current (not superseded) cost by currency and charge category. Currencies are never combined,
    and billed and effective cost are separate measures (a commitment purchase has billed cost and zero
    effective cost; the usage it covers carries the amortized effective cost)."""
    rows = db.execute(
        text(
            "select r.billing_currency, r.charge_category, count(*) n, sum(r.billed_cost), "
            "sum(r.effective_cost), sum(r.list_cost), sum(r.contracted_cost) "
            "from focus_cost_records r where not exists (select 1 from focus_supersessions s "
            "where s.tenant_id = r.tenant_id and s.record_id = r.id) "
            "group by 1, 2 order by 1, 2"
        )
    ).all()
    return [
        {
            "currency": c,
            "charge_category": cat,
            "lines": n,
            "billed": b,
            "effective": e,
            "list": ls,
            "contracted": ct,
        }
        for c, cat, n, b, e, ls, ct in rows
    ]


def zero() -> Decimal:
    return Decimal(0)
