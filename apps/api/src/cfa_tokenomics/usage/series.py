"""Bucketed time series for the telemetry view (ADR 0009).

Rules that keep the numbers honest:
- One category per query. Categories are never combined.
- ``source_type`` is always part of the series key, so two sources describing the same traffic
  are returned as separate series and never added.
- Within a source, windows and models are disjoint, so summing them into a bucket is valid.
- Provider windows longer than the bucket cannot be split, so they are counted and left out.
- A bucket with no data has no point (unknown, not zero).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.orm import Session

from ..db import AggregateObservationRow, RequestObservationRow
from .models import CATEGORIES, SKUS, SOURCE_TYPES

BUCKETS = {"hour": timedelta(hours=1), "day": timedelta(days=1)}
GROUPABLE = ("provider", "sku", "model_id", "account")
MAX_RANGE = {"hour": timedelta(days=7), "day": timedelta(days=92)}
MAX_ROWS = 20000
_REQ_COLUMN = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read": "cache_read_tokens",
    "cache_write": "cache_write_tokens",
    "reasoning": "reasoning_tokens",
    "total": "provider_total",
}


class SeriesError(ValueError):
    pass


@dataclass
class _Acc:
    points: dict[datetime, list]  # bucket -> [value, partial]


def _scope(model, allowed):
    if allowed is None:
        return None
    if not allowed:
        return literal(False)
    return or_(*[and_(model.provider == p, model.account == a) for p, a in allowed])


def series(
    db: Session,
    start: datetime,
    end: datetime,
    category: str,
    bucket: str = "hour",
    group_by: tuple[str, ...] = ("provider",),
    provider: str | None = None,
    account: str | None = None,
    model_id: str | None = None,
    sku: str | None = None,
    source_type: str | None = None,
    allowed: list[tuple[str, str]] | None = None,
) -> dict:
    if start.tzinfo is None or end.tzinfo is None:
        raise SeriesError("start and end must include a timezone")
    if end <= start:
        raise SeriesError("end must be after start")
    if bucket not in BUCKETS:
        raise SeriesError("bucket must be hour or day")
    if end - start > MAX_RANGE[bucket]:
        raise SeriesError(f"range exceeds {MAX_RANGE[bucket].days} days for bucket {bucket}")
    if category not in CATEGORIES:
        raise SeriesError("unknown category")
    if sku is not None and sku not in SKUS:
        raise SeriesError("unknown sku")
    if source_type is not None and source_type not in SOURCE_TYPES:
        raise SeriesError("unknown source_type")
    bad = [g for g in group_by if g not in GROUPABLE]
    if bad:
        raise SeriesError(f"cannot group by {bad[0]}")
    dims = tuple(dict.fromkeys(group_by))  # de-duplicate, keep order
    span = BUCKETS[bucket]

    def filters(model, stmt):
        for col, val in (
            ("provider", provider),
            ("account", account),
            ("model_id", model_id),
            ("sku", sku),
            ("source_type", source_type),
        ):
            if val is not None:
                stmt = stmt.where(getattr(model, col) == val)
        scope = _scope(model, allowed)
        return stmt if scope is None else stmt.where(scope)

    out: dict[tuple, _Acc] = {}
    latest: dict[tuple[str, str], datetime] = {}
    truncated = False

    # Provider aggregates.
    A = AggregateObservationRow
    b = func.date_trunc(bucket, A.window_start, "UTC").label("b")
    cols = [getattr(A, d) for d in dims]
    q = filters(
        A,
        select(
            b, *cols, A.source_type, func.sum(A.value), func.bool_or(A.quality == "partial")
        ).where(
            A.category == category,
            A.window_start >= start,
            A.window_start < end,
            (A.window_end - A.window_start) <= span,
        ),
    ).group_by(b, *cols, A.source_type)
    rows = db.execute(q.limit(MAX_ROWS + 1)).all()
    truncated |= len(rows) > MAX_ROWS
    for r in rows[:MAX_ROWS]:
        key = (*r[1 : 1 + len(dims)], r[1 + len(dims)])
        out.setdefault(key, _Acc({})).points[r[0]] = [float(r[-2]), bool(r[-1])]

    excluded = db.scalar(
        filters(
            A,
            select(func.count()).where(
                A.category == category,
                A.window_start >= start,
                A.window_start < end,
                (A.window_end - A.window_start) > span,
            ),
        )
    )
    for p, st, at in db.execute(
        filters(
            A,
            select(A.provider, A.source_type, func.max(A.window_end)).where(A.category == category),
        ).group_by(A.provider, A.source_type)
    ):
        latest[(p, st)] = at

    # Requests routed through the app. Rows without this category are unknown and excluded.
    R = RequestObservationRow
    col = getattr(R, _REQ_COLUMN[category])
    rb = func.date_trunc(bucket, R.occurred_at, "UTC").label("b")
    rcols = [getattr(R, d) for d in dims]
    rq = filters(
        R,
        select(rb, *rcols, R.source_type, func.sum(col)).where(
            col.is_not(None), R.occurred_at >= start, R.occurred_at < end
        ),
    ).group_by(rb, *rcols, R.source_type)
    rrows = db.execute(rq.limit(MAX_ROWS + 1)).all()
    truncated |= len(rrows) > MAX_ROWS
    for r in rrows[:MAX_ROWS]:
        key = (*r[1 : 1 + len(dims)], r[1 + len(dims)])
        out.setdefault(key, _Acc({})).points[r[0]] = [float(r[-1]), False]

    result = []
    for key, acc in sorted(out.items(), key=lambda kv: tuple(str(x) for x in kv[0])):
        result.append(
            {
                "key": {**dict(zip(dims, key[:-1], strict=True)), "source_type": key[-1]},
                "points": [
                    {"t": t, "value": v, "partial": p} for t, (v, p) in sorted(acc.points.items())
                ],
            }
        )
    return {
        "range": {"start": start, "end": end},
        "bucket": bucket,
        "category": category,
        "group_by": list(dims),
        "series": result,
        "latest_window_end": [
            {"provider": p, "source_type": st, "at": at} for (p, st), at in sorted(latest.items())
        ],
        "excluded_windows": excluded or 0,
        "truncated": truncated,
        "notes": [
            "One token category per query; categories are never combined.",
            "Sources are separate series and are never added together.",
            "A bucket with no data has no point; unknown is not zero.",
        ],
    }
