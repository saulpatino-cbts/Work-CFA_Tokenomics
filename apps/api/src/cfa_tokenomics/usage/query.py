"""Read model: reconciled usage for a bounded time range (ADR 0007).

Rows are produced per provider aggregate window. Request observations outside every
aggregate window for a key are reported once as an ``app_only`` row for the queried range.
Nothing is added across sources.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..db import AggregateObservationRow, CollectionCheckpoint, RequestObservationRow
from .models import CATEGORIES, RequestObservation
from .reconcile import Reconciled, reconcile

MAX_RANGE = timedelta(days=31)
MAX_ROWS = 5000

_COLUMN = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read": "cache_read_tokens",
    "cache_write": "cache_write_tokens",
    "reasoning": "reasoning_tokens",
    "total": "provider_total",
}


class QueryError(ValueError):
    pass


@dataclass(frozen=True)
class UsageRow:
    provider: str
    account: str
    model_id: str
    category: str
    window_start: datetime
    window_end: datetime
    status: str
    app_observed: int | None
    provider_reported: float | None
    total: float | None
    unattributed: float | None
    partial: bool
    aggregate_quality: str | None
    aggregate_revision: int | None
    sku: str = "unknown"
    source_type: str = "app_routed"


def _to_obs(r: RequestObservationRow) -> RequestObservation:
    return RequestObservation(
        provider=r.provider,
        account=r.account,
        request_id=r.source_key,
        attempt=1,
        model_id=r.model_id,
        occurred_at=r.occurred_at,
        input=r.input_tokens,
        output=r.output_tokens,
        cache_read=r.cache_read_tokens,
        cache_write=r.cache_write_tokens,
        reasoning=r.reasoning_tokens,
        total=r.provider_total,
    )


def _row(
    key, start, end, rec: Reconciled, agg, sku="unknown", source_type="app_routed"
) -> UsageRow:
    provider, account, model = key
    return UsageRow(
        provider, account, model, rec.category, start, end, rec.status.value,
        rec.app_observed, rec.provider_reported, rec.total, rec.unattributed, rec.partial,
        agg.quality if agg else None, agg.revision if agg else None, sku, source_type,
    )  # fmt: skip


def usage(
    db: Session,
    start: datetime,
    end: datetime,
    provider: str | None = None,
    account: str | None = None,
    model_id: str | None = None,
    allowed: list[tuple[str, str]] | None = None,
    sku: str | None = None,
    source_type: str | None = None,
) -> dict:
    """``allowed`` is the caller's (provider, account) scope; None means unrestricted (admin).

    An empty list returns nothing: access is denied by default.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise QueryError("start and end must include a timezone")
    if end <= start:
        raise QueryError("end must be after start")
    if end - start > MAX_RANGE:
        raise QueryError(f"range exceeds {MAX_RANGE.days} days")

    def scoped(stmt, model):
        for col, val in (
            ("provider", provider),
            ("account", account),
            ("model_id", model_id),
            ("sku", sku),
            ("source_type", source_type),
        ):
            if val is not None:
                stmt = stmt.where(getattr(model, col) == val)
        if allowed is not None:
            stmt = stmt.where(
                or_(
                    *[
                        and_(model.provider == p, model.account == a)  # type: ignore[attr-defined]
                        for p, a in allowed
                    ]
                )
                if allowed
                else False
            )
        return stmt

    aggs = db.scalars(
        scoped(
            select(AggregateObservationRow).where(
                AggregateObservationRow.window_start < end,
                AggregateObservationRow.window_end > start,
            ),
            AggregateObservationRow,
        ).limit(MAX_ROWS + 1)
    ).all()
    reqs = db.scalars(
        scoped(
            select(RequestObservationRow).where(
                RequestObservationRow.occurred_at >= start, RequestObservationRow.occurred_at < end
            ),
            RequestObservationRow,
        ).limit(MAX_ROWS + 1)
    ).all()
    truncated = len(aggs) > MAX_ROWS or len(reqs) > MAX_ROWS
    aggs, reqs = aggs[:MAX_ROWS], reqs[:MAX_ROWS]

    by_key: dict[tuple, list[RequestObservationRow]] = {}
    for r in reqs:
        by_key.setdefault((r.provider, r.account, r.model_id), []).append(r)

    rows: list[UsageRow] = []
    covered: dict[tuple, set[int]] = {}
    for a in sorted(aggs, key=lambda a: (a.provider, a.account, a.model_id, a.window_start)):
        key = (a.provider, a.account, a.model_id)
        inside = [r for r in by_key.get(key, []) if a.window_start <= r.occurred_at < a.window_end]
        covered.setdefault(key, set()).update(r.id for r in inside)
        obs = [_to_obs(r) for r in inside]
        rec = reconcile(a.category, obs, a.value)
        rows.append(_row(key, a.window_start, a.window_end, rec, a, a.sku, a.source_type))
    for key, rs in by_key.items():
        left = [r for r in rs if r.id not in covered.get(key, set())]
        if not left:
            continue
        obs = [_to_obs(r) for r in left]
        for cat in CATEGORIES:
            if any(getattr(r, _COLUMN[cat]) is not None for r in left):
                skus = {r.sku for r in left}
                one = skus.pop() if len(skus) == 1 else "unknown"
                rows.append(_row(key, start, end, reconcile(cat, obs, None), None, one))

    checkpoints = db.scalars(select(CollectionCheckpoint)).all()
    fresh = [
        {"provider": c.provider, "account": c.account, "checkpoint_updated_at": c.updated_at}
        for c in checkpoints
        if (provider is None or c.provider == provider)
        and (account is None or c.account == account)
        and (allowed is None or (c.provider, c.account) in allowed)
    ]
    return {
        "range": {"start": start, "end": end},
        "rows": [asdict(r) for r in rows],
        "freshness": fresh,
        "truncated": truncated,
        "notes": [
            "Provider and application observations are never added together.",
            "unattributed is traffic the provider reported that the app did not route.",
            "Unknown values are null, never zero.",
        ],
    }
