"""Project the usage ledger into normalized usage facts (Phase 1 slice 7).

The ledger stays the record; facts are a derived, rebuildable layer in the shape the economics model
needs: one exact-decimal quantity per measure, with a unit, a basis and a pointer to its source row.

Rules that matter:
- A category the source did not report produces no fact. Unknown is not zero.
- Quality maps to basis conservatively: reported and partial are observed (partial keeps its quality
  flag), estimated is estimated, and unknown is estimated, never observed.
- Float aggregates are converted through their shortest round-trip text, so an integer count is
  exact and a fraction is the same decimal the provider's number printed as.
- Non-finite values are skipped and counted, not stored.
- The projection is idempotent. Requests never change; an aggregate fact is revised only when its
  source row has a higher revision.
Expects a session from ``tenancy.tenant_session``: only that tenant's ledger rows are visible.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

_BASIS = (
    "case {q}.quality when 'reported' then 'observed' when 'partial' then 'observed' "
    "else 'estimated' end"
)

_REQUESTS = text(
    "insert into usage_facts (id, tenant_id, grain, provider, account, model_id, sku, source_type, "
    "measure, statistic, quantity, unit, period_start, period_end, basis, quality, revision, "
    "normalization_version, source_table, source_id) "
    "select gen_random_uuid(), r.tenant_id, 'request', r.provider, r.account, r.model_id, r.sku, "
    "r.source_type, m.measure, null, m.qty, 'tokens', r.occurred_at, r.occurred_at, "
    f"{_BASIS.format(q='r')}, r.quality, 1, r.normalization_version, "
    "'usage_request_observations', r.id "
    "from usage_request_observations r cross join lateral (values "
    "('input', r.input_tokens), ('output', r.output_tokens), ('cache_read', r.cache_read_tokens), "
    "('cache_write', r.cache_write_tokens), ('reasoning', r.reasoning_tokens), "
    "('total', r.provider_total)) as m(measure, qty) "
    "where m.qty is not null "
    "on conflict (tenant_id, source_table, source_id, measure) do nothing "
    "returning source_id"
)

_FINITE = "a.value <> 'NaN'::float8 and a.value <> 'Infinity'::float8"

_AGG_NEW = text(
    "insert into usage_facts (id, tenant_id, grain, provider, account, model_id, sku, source_type, "
    "measure, statistic, quantity, unit, period_start, period_end, basis, quality, revision, "
    "normalization_version, source_table, source_id) "
    "select gen_random_uuid(), a.tenant_id, 'window', a.provider, a.account, a.model_id, a.sku, "
    "a.source_type, a.category, a.statistic, a.value::text::numeric, 'tokens', a.window_start, "
    f"a.window_end, {_BASIS.format(q='a')}, a.quality, a.revision, a.normalization_version, "
    "'usage_aggregate_observations', a.id "
    f"from usage_aggregate_observations a where {_FINITE} "
    "on conflict (tenant_id, source_table, source_id, measure) do nothing returning id"
)

_AGG_REVISE = text(
    "update usage_facts f set quantity = a.value::text::numeric, "
    f"basis = {_BASIS.format(q='a')}, quality = a.quality, revision = a.revision, "
    "normalization_version = a.normalization_version, updated_at = now() "
    "from usage_aggregate_observations a "
    "where f.source_table = 'usage_aggregate_observations' and f.source_id = a.id "
    f"and f.measure = a.category and a.revision > f.revision and {_FINITE} returning f.id"
)

_AGG_TOTAL = text(
    f"select count(*) filter (where {_FINITE}), count(*) filter (where not ({_FINITE})) "
    "from usage_aggregate_observations a"
)


@dataclass(frozen=True)
class ProjectionResult:
    request_rows: int
    request_facts: int
    aggregate_inserted: int
    aggregate_revised: int
    aggregate_unchanged: int
    skipped_nonfinite: int


def project_usage(db: Session) -> ProjectionResult:
    """Bring the facts up to date with the ledger. Safe to run again and again."""
    req = db.execute(_REQUESTS).scalars().all()
    new = len(db.execute(_AGG_NEW).scalars().all())
    revised = len(db.execute(_AGG_REVISE).scalars().all())
    finite, skipped = db.execute(_AGG_TOTAL).one()
    db.commit()
    return ProjectionResult(
        request_rows=len(set(req)), request_facts=len(req), aggregate_inserted=new,
        aggregate_revised=revised, aggregate_unchanged=finite - new - revised,
        skipped_nonfinite=skipped,
    )  # fmt: skip
