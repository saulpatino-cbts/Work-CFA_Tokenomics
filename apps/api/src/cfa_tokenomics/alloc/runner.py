"""Allocation storage and runs.

- Rules and drivers are append-only and versioned. The current rule set is the latest version of each key
  that is enabled; disabling is a new version.
- A run allocates every current (not superseded) cost line whose charge period starts in the window. It is
  one transaction, and it is skipped when an identical run (same rules, drivers and cost lines) already
  succeeded, so re-running changes nothing.
- "Current allocation" of a line is the slices from the latest successful run that included it, where
  latest means the highest run sequence number (never a clock comparison).
- Reports keep three buckets apart: allocated to an application, explicitly unallocated (with a reason),
  and not yet allocated (no run has covered the line, for example after a revised import).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import insert, select, text
from sqlalchemy.orm import Session

from ..models_econ import Application, Workload
from . import tables as T
from .engine import MEASURES, Condition, Context, CostLine, Rule, allocate_line, validate_rule

CHUNK = 1000
_COLUMN = {
    "billed": "billed_cost",
    "effective": "effective_cost",
    "list": "list_cost",
    "contracted": "contracted_cost",
}
_FIELD_COLUMNS = (
    "service_name", "service_category", "service_subcategory", "service_provider_name",
    "host_provider_name", "invoice_issuer_name", "resource_id", "resource_name", "resource_type",
    "sub_account_id", "billing_account_id", "region_id", "sku_id", "charge_category", "charge_class",
    "pricing_category", "commitment_discount_id", "billing_currency", "allocated_method_id",
    "allocated_resource_id",
)  # fmt: skip


class AllocationError(Exception):
    pass


@dataclass
class RunResult:
    status: str  # succeeded, unchanged, failed
    run_id: uuid.UUID | None = None
    lines: int = 0
    slices: int = 0
    error: str | None = None


@dataclass
class Summary:
    currency: str
    total_effective: Decimal
    allocated_effective: Decimal
    unallocated_effective: Decimal
    not_yet_allocated_effective: Decimal
    coverage: Decimal | None  # allocated / total effective, None when the total is zero
    by_method: dict[str, Decimal] = field(default_factory=dict)
    unallocated_by_reason: dict[str, Decimal] = field(default_factory=dict)
    provider_split_lines: int = 0


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


# ---- rules and drivers -----------------------------------------------------------------------------


def create_rule(
    db: Session,
    tenant_id: uuid.UUID,
    key: str,
    name: str,
    priority: int,
    method: str,
    params: dict,
    author: str,
    conditions: list[dict] | None = None,
    enabled: bool = True,
) -> int:
    """Append a new version of a rule and return its version number. Validated before it is stored,
    and every application it names must exist in this tenant."""
    conds = tuple(Condition(c["field"], c["op"], c.get("value")) for c in (conditions or []))
    validate_rule(method, params, conds)
    named = _application_ids(method, params)
    if named:
        found = set(db.scalars(select(Application.id).where(Application.id.in_(named))))
        if found != set(named):
            raise AllocationError("a rule names an application that does not exist")
    workload = params.get("workload_id") if method == "direct" else None
    if (
        workload
        and db.scalar(select(Workload.id).where(Workload.id == uuid.UUID(str(workload)))) is None
    ):
        raise AllocationError("a rule names a workload that does not exist")
    latest = db.execute(
        text("select max(version) from allocation_rules where rule_key = :k"), {"k": key}
    ).scalar()
    version = (latest or 0) + 1
    db.execute(
        insert(T.allocation_rules).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            rule_key=key,
            version=version,
            name=name,
            priority=priority,
            enabled=enabled,
            method=method,
            conditions=[{"field": c.field, "op": c.op, "value": c.value} for c in conds],
            params=params,
            author=author,
        )  # fmt: skip
    )
    db.commit()
    return version


def _application_ids(method: str, params: dict) -> list[uuid.UUID]:
    if method == "direct":
        ids = [params["application_id"]]
    elif method == "tag":
        ids = list((params.get("map") or {}).values())
    elif method == "fixed_percent":
        ids = [t["application_id"] for t in params["targets"]]
    else:
        ids = list(params["application_ids"])
    return [uuid.UUID(str(i)) for i in ids]


def add_driver(
    db: Session,
    tenant_id: uuid.UUID,
    rule_key: str,
    application_id: uuid.UUID,
    period_start: datetime,
    period_end: datetime,
    value: Decimal,
    basis: str,
    source: str,
    author: str,
) -> int:
    """Record a driver value (for example tokens used by an application in a month). A change is a new
    version. The source says where the number came from, and the basis says how much to trust it."""
    latest = db.execute(
        text(
            "select max(version) from allocation_drivers where rule_key = :k and application_id = :a "
            "and period_start = :s"
        ),
        {"k": rule_key, "a": application_id, "s": period_start},
    ).scalar()
    version = (latest or 0) + 1
    db.execute(
        insert(T.allocation_drivers).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            rule_key=rule_key,
            application_id=application_id,
            period_start=period_start,
            period_end=period_end,
            value=value,
            basis=basis,
            source=source,
            version=version,
            author=author,
        )  # fmt: skip
    )
    db.commit()
    return version


def current_rules(db: Session) -> list[Rule]:
    rows = db.execute(
        text(
            "select distinct on (rule_key) rule_key, version, priority, enabled, method, conditions, params "
            "from allocation_rules order by rule_key, version desc"
        )
    ).all()
    return [
        Rule(
            k, v, p, m, tuple(Condition(c["field"], c["op"], c.get("value")) for c in conds), params
        )
        for k, v, p, enabled, m, conds, params in rows
        if enabled
    ]


def _context(db: Session) -> tuple[Context, list[tuple]]:
    ctx = Context(
        apps_by_name={n: i for i, n in db.execute(select(Application.id, Application.name)).all()}
    )
    rows = db.execute(
        text(
            "select rule_key, application_id, period_start, period_end, version, value from allocation_drivers"
        )
    ).all()
    for k, a, s, e, v, val in rows:
        ctx.drivers.setdefault((k, a), []).append((s, e, v, val))
    return ctx, [(k, str(a), s.isoformat(), v) for k, a, s, _e, v, _val in rows]


def _lines(db: Session, start: datetime, end: datetime) -> list[CostLine]:
    cols = ", ".join(_FIELD_COLUMNS)
    rows = db.execute(
        text(
            f"select r.id, r.billed_cost, r.effective_cost, r.list_cost, r.contracted_cost, "
            f"r.charge_period_start, r.tags, {cols} from focus_cost_records r "
            "where r.charge_period_start >= :s and r.charge_period_start < :e "
            "and not exists (select 1 from focus_supersessions s where s.tenant_id = r.tenant_id "
            "and s.record_id = r.id) order by r.id"
        ),
        {"s": start, "e": end},
    ).mappings()
    return [
        CostLine(
            id=r["id"],
            amounts={
                "billed": r["billed_cost"],
                "effective": r["effective_cost"],
                "list": r["list_cost"],
                "contracted": r["contracted_cost"],
            },
            fields={c: r[c] for c in _FIELD_COLUMNS},
            tags=r["tags"] or {},
            charge_period_start=r["charge_period_start"],
        )
        for r in rows
    ]


# ---- running ---------------------------------------------------------------------------------------


def run_allocation(
    db: Session,
    tenant_id: uuid.UUID,
    window_start: datetime,
    window_end: datetime,
    created_by: str,
    now: datetime | None = None,
) -> RunResult:
    now = now or datetime.now(UTC)
    rules = current_rules(db)
    ctx, driver_keys = _context(db)
    lines = _lines(db, window_start, window_end)
    rules_hash = hashlib.sha256(
        _canon(
            [
                (
                    r.key,
                    r.version,
                    r.priority,
                    r.method,
                    [(c.field, c.op, c.value) for c in r.conditions],
                    r.params,
                )
                for r in rules
            ]
        ).encode()
    ).hexdigest()
    inputs_hash = hashlib.sha256(
        _canon(
            [
                rules_hash,
                sorted(str(ln.id) for ln in lines),
                sorted(driver_keys),
                sorted(ctx.apps_by_name.items(), key=str),
            ]
        ).encode()
    ).hexdigest()
    same = db.execute(
        text(
            "select id, line_count, slice_count from allocation_runs where status = 'succeeded' "
            "and window_start = :s and window_end = :e and inputs_hash = :h limit 1"
        ),
        {"s": window_start, "e": window_end, "h": inputs_hash},
    ).first()
    if same:
        return RunResult("unchanged", same[0], same[1], same[2])

    run_id = uuid.uuid4()
    db.execute(
        insert(T.allocation_runs).values(
            id=run_id,
            tenant_id=tenant_id,
            window_start=window_start,
            window_end=window_end,
            status="running",
            rules_hash=rules_hash,
            inputs_hash=inputs_hash,
            line_count=0,
            slice_count=0,
            created_by=created_by,
        )  # fmt: skip
    )
    try:
        with db.begin_nested():
            batch: list[dict] = []
            total_slices = 0
            for ln in lines:
                for s in allocate_line(ln, rules, ctx):
                    batch.append(
                        {
                            "id": uuid.uuid4(),
                            "tenant_id": tenant_id,
                            "allocation_run_id": run_id,
                            "focus_cost_id": ln.id,
                            "application_id": s.application_id,
                            "workload_id": s.workload_id,
                            "rule_key": s.rule_key,
                            "rule_version": s.rule_version,
                            "method": s.method,
                            "reason": s.reason,
                            "share": s.share,
                            "billing_currency": ln.fields["billing_currency"],
                            **{_COLUMN[m]: s.amounts[m] for m in MEASURES},
                        }  # fmt: skip
                    )
                    total_slices += 1
                if len(batch) >= CHUNK:
                    db.execute(insert(T.allocated_costs), batch)
                    batch = []
            if batch:
                db.execute(insert(T.allocated_costs), batch)
        db.execute(
            text(
                "update allocation_runs set status = 'succeeded', line_count = :n, slice_count = :c, "
                "finished_at = :t where id = :r"
            ),
            {"n": len(lines), "c": total_slices, "t": now, "r": run_id},
        )
        db.commit()
    except Exception as exc:  # no slices from a failed run may remain
        db.rollback()
        msg = f"allocation failed: {type(exc).__name__}"
        db.execute(
            insert(T.allocation_runs).values(
                id=run_id,
                tenant_id=tenant_id,
                window_start=window_start,
                window_end=window_end,
                status="failed",
                rules_hash=rules_hash,
                inputs_hash=inputs_hash,
                line_count=0,
                slice_count=0,
                created_by=created_by,
                finished_at=now,
                error=msg,
            )  # fmt: skip
        )
        db.commit()
        return RunResult("failed", run_id, error=msg)
    return RunResult("succeeded", run_id, len(lines), total_slices)


# ---- reports ---------------------------------------------------------------------------------------

_LATEST = (
    "latest as (select distinct on (a.focus_cost_id) a.focus_cost_id, a.allocation_run_id "
    "from allocated_costs a join allocation_runs r on r.tenant_id = a.tenant_id and r.id = a.allocation_run_id "
    "where r.status = 'succeeded' order by a.focus_cost_id, r.seq desc)"
)
_CURRENT = (
    "current_lines as (select c.* from focus_cost_records c where not exists "
    "(select 1 from focus_supersessions s where s.tenant_id = c.tenant_id and s.record_id = c.id))"
)


def allocation_summary(db: Session) -> list[Summary]:
    """Per currency (never combined): how much current effective cost is allocated, explicitly
    unallocated, or not yet allocated, plus the coverage ratio."""
    # Line totals and slice totals are computed separately: joining lines to their slices would count a
    # line once per slice and overstate the denominator.
    sql = text(
        f"with {_CURRENT}, {_LATEST}, "
        "tot as (select c.billing_currency cur, sum(c.effective_cost) total, "
        " coalesce(sum(c.effective_cost) filter (where not exists "
        "  (select 1 from latest l where l.focus_cost_id = c.id)), 0) not_yet, "
        " count(*) filter (where c.allocated_method_id is not null) split_lines "
        " from current_lines c group by c.billing_currency), "
        "al as (select c.billing_currency cur, "
        " coalesce(sum(a.effective_cost) filter (where a.application_id is not null), 0) allocated, "
        " coalesce(sum(a.effective_cost) filter (where a.application_id is null), 0) unalloc "
        " from current_lines c join latest l on l.focus_cost_id = c.id "
        " join allocated_costs a on a.tenant_id = c.tenant_id and a.focus_cost_id = c.id "
        "  and a.allocation_run_id = l.allocation_run_id group by c.billing_currency) "
        "select tot.cur, tot.total, coalesce(al.allocated, 0), coalesce(al.unalloc, 0), tot.not_yet, "
        " tot.split_lines from tot left join al on al.cur = tot.cur order by tot.cur"
    )
    out: list[Summary] = []
    for cur, total, allocated, unalloc, not_yet, split in db.execute(sql).all():
        cov = (allocated / total) if total != 0 else None
        s = Summary(cur, total, allocated, unalloc, not_yet, cov, provider_split_lines=split)
        for method, reason, amount in db.execute(
            text(
                f"with {_CURRENT}, {_LATEST} select a.method, a.reason, sum(a.effective_cost) "
                "from current_lines c join latest l on l.focus_cost_id = c.id "
                "join allocated_costs a on a.tenant_id = c.tenant_id and a.focus_cost_id = c.id "
                "and a.allocation_run_id = l.allocation_run_id where c.billing_currency = :cur "
                "group by 1, 2"
            ),
            {"cur": cur},
        ):
            if method == "unallocated" or reason == "percent_remainder":
                s.unallocated_by_reason[reason or "unknown"] = (
                    s.unallocated_by_reason.get(reason or "unknown", Decimal(0)) + amount
                )
            if method != "unallocated":
                s.by_method[method] = s.by_method.get(method, Decimal(0)) + amount
        out.append(s)
    return out


def allocated_cost_by_application(db: Session) -> list[dict]:
    """Current allocated cost per application and currency (feeds application economics)."""
    rows = db.execute(
        text(
            f"with {_CURRENT}, {_LATEST} select a.application_id, a.billing_currency, "
            "sum(a.billed_cost), sum(a.effective_cost), sum(a.list_cost), sum(a.contracted_cost), count(*) "
            "from current_lines c join latest l on l.focus_cost_id = c.id "
            "join allocated_costs a on a.tenant_id = c.tenant_id and a.focus_cost_id = c.id "
            "and a.allocation_run_id = l.allocation_run_id where a.application_id is not null "
            "group by 1, 2 order by 1, 2"
        )
    ).all()
    return [
        {
            "application_id": a,
            "currency": cur,
            "billed": b,
            "effective": e,
            "list": ls,
            "contracted": ct,
            "slices": n,
        }
        for a, cur, b, e, ls, ct, n in rows
    ]


def verify_allocation(db: Session) -> list[dict]:
    """Cost lines whose latest allocation does not add up to the original in any measure. Must be empty."""
    rows = db.execute(
        text(
            f"with {_CURRENT}, {_LATEST} select c.id, "
            "c.billed_cost - sum(a.billed_cost), c.effective_cost - sum(a.effective_cost), "
            "c.list_cost - sum(a.list_cost), c.contracted_cost - sum(a.contracted_cost) "
            "from current_lines c join latest l on l.focus_cost_id = c.id "
            "join allocated_costs a on a.tenant_id = c.tenant_id and a.focus_cost_id = c.id "
            "and a.allocation_run_id = l.allocation_run_id "
            "group by c.id, c.billed_cost, c.effective_cost, c.list_cost, c.contracted_cost "
            "having c.billed_cost <> sum(a.billed_cost) or c.effective_cost <> sum(a.effective_cost) "
            "or c.list_cost <> sum(a.list_cost) or c.contracted_cost <> sum(a.contracted_cost)"
        )
    ).all()
    return [
        {"focus_cost_id": i, "billed": b, "effective": e, "list": ls, "contracted": ct}
        for i, b, e, ls, ct in rows
    ]
