"""AI model billing from FOCUS cost rows (FOCUS 1.5 working draft, supported feature "AI Model Billing").

Reads tokens, cost and model identity from rows already imported, so nothing here calls a vendor. The
queries follow the draft's own example queries and caveats (docs/economics/08-focus-1-5-readiness.md):

- Only ChargeCategory "Usage" rows of ServiceCategory "AI and Machine Learning" with ConsumedUnit "Tokens".
- Token quantities exclude correction rows (ChargeClass not null), as the draft's token queries do;
  corrections are reported as their own cost line so money is never hidden.
- Rows whose unit is token-like but not exactly "Tokens" ("1000 Tokens", "Token") are not summed and
  are counted in ``rows_with_other_token_units``.
- Model identity and token direction and cache action come from SkuPriceDetails properties
  (ModelDeveloper, ModelFamily, ModelId, ModelVersion, TokenDirection, TokenCacheAction). They are
  recommended, not mandatory, so many rows will lack them: a row without a direction is counted as
  unclassified, never guessed from a meter name. A value outside the allowed set is treated as absent
  and counted.
- The draft says a conforming ConsumedQuantity does not double count a cached token on two rows, so the
  rows can be summed. That is the draft's rule, not something this code can verify of a given provider.
- Cache hit rate is cache-read tokens over all input tokens, and is unknown (None) when no input row
  says whether its tokens touched a cache. If a provider emits cache-read rows but
  none for its other input tokens, the rate is overstated; the result carries a warning when that shape
  is seen. Unknown is None, never zero.
Expects a session from ``tenancy.tenant_session``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..econ.types import exact

DIRECTIONS = ("Input", "Output")
CACHE_ACTIONS = ("Uncached", "Read", "Write", "Other")
MILLION = Decimal(1_000_000)
MAX_ROWS = 5000

_SQL = text(
    "with cur as (select r.* from focus_cost_records r where not exists "
    " (select 1 from focus_supersessions s where s.tenant_id = r.tenant_id and s.record_id = r.id)) "
    "select service_provider_name provider, "
    " sku_price_details->>'ModelDeveloper' developer, sku_price_details->>'ModelFamily' family, "
    " sku_price_details->>'ModelId' model_id, sku_price_details->>'ModelVersion' model_version, "
    " sku_price_details->>'TokenDirection' direction, sku_price_details->>'TokenCacheAction' cache_action, "
    " sku_id, sku_price_id, sku_meter, pricing_unit, billing_currency currency, "
    " (charge_class is not null) is_correction, "
    " sum(consumed_quantity) tokens, sum(pricing_quantity) pricing_quantity, "
    " sum(effective_cost) effective_cost, sum(billed_cost) billed_cost, count(*) lines "
    "from cur where charge_category = 'Usage' and service_category = 'AI and Machine Learning' "
    " and consumed_unit = 'Tokens' and charge_period_start >= :s and charge_period_end <= :e "
    "group by 1,2,3,4,5,6,7,8,9,10,11,12,13 order by 1,4,6,7,8,9 limit :lim"
)


# Token-like units that are not exactly "Tokens" (for example "1000 Tokens" or "Token"). The draft's own
# queries match "Tokens" exactly, and a unit with a quantity changes what a quantity means, so these rows
# are not summed. They are counted so they are never silently missing.
_OTHER_UNITS = text(
    "with cur as (select r.* from focus_cost_records r where not exists "
    " (select 1 from focus_supersessions s where s.tenant_id = r.tenant_id and s.record_id = r.id)) "
    "select count(*) from cur where charge_category = 'Usage' and service_category = 'AI and Machine Learning' "
    " and consumed_unit ilike '%token%' and consumed_unit <> 'Tokens' "
    " and charge_period_start >= :s and charge_period_end <= :e"
)


@dataclass
class Row:
    provider: str | None
    developer: str | None
    family: str | None
    model_id: str | None
    model_version: str | None
    direction: str | None  # Input, Output, or None when the provider did not say
    cache_action: str | None
    sku_id: str | None
    sku_price_id: str | None
    sku_meter: str | None
    pricing_unit: str | None
    currency: str
    is_correction: bool
    tokens: Decimal | None
    pricing_quantity: Decimal | None
    effective_cost: Decimal
    billed_cost: Decimal
    lines: int
    effective_cost_per_million_tokens: Decimal | None = None


@dataclass
class ModelSummary:
    provider: str | None
    model_id: str | None  # None: the provider did not state a model
    currency: str
    input_tokens: Decimal | None = None
    output_tokens: Decimal | None = None
    cache_read_tokens: Decimal | None = None
    cache_write_tokens: Decimal | None = None
    unclassified_tokens: Decimal = Decimal(0)  # token rows with no usable direction
    effective_cost: Decimal = Decimal(0)  # corrections excluded
    correction_effective_cost: Decimal = Decimal(0)
    input_to_output_ratio: Decimal | None = None
    cache_hit_rate: Decimal | None = None
    cache_labelled: bool = False  # some input row says whether its tokens touched a cache
    warnings: list[str] = field(default_factory=list)


@dataclass
class AiTokenReport:
    rows: list[Row]
    models: list[ModelSummary]
    truncated: bool
    rows_without_model: int
    rows_without_direction: int
    rows_with_invalid_values: int
    rows_with_other_token_units: int = 0


def _clean(value: str | None, allowed: tuple[str, ...]) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    return (value, False) if value in allowed else (None, True)


@exact
def _per_million(cost: Decimal, tokens: Decimal | None) -> Decimal | None:
    return None if not tokens else cost * MILLION / tokens


def _add(a: Decimal | None, b: Decimal | None) -> Decimal | None:
    if b is None:
        return a
    return b if a is None else a + b


@exact
def _ratio(n: Decimal | None, d: Decimal | None) -> Decimal | None:
    return None if n is None or not d else n / d


def ai_token_report(db: Session, start: datetime, end: datetime) -> AiTokenReport:
    raw = db.execute(_SQL, {"s": start, "e": end, "lim": MAX_ROWS + 1}).all()
    truncated = len(raw) > MAX_ROWS
    rows: list[Row] = []
    invalid = 0
    for r in raw[:MAX_ROWS]:
        direction, bad_d = _clean(r.direction, DIRECTIONS)
        action, bad_c = _clean(r.cache_action, CACHE_ACTIONS)
        invalid += bad_d or bad_c
        row = Row(
            r.provider, r.developer, r.family, r.model_id, r.model_version, direction, action, r.sku_id,
            r.sku_price_id, r.sku_meter, r.pricing_unit, r.currency, bool(r.is_correction), r.tokens,
            r.pricing_quantity, r.effective_cost, r.billed_cost, r.lines,
        )  # fmt: skip
        if not row.is_correction:
            row.effective_cost_per_million_tokens = _per_million(row.effective_cost, row.tokens)
        rows.append(row)

    models: dict[tuple, ModelSummary] = {}
    for row in rows:
        m = models.setdefault(
            (row.provider, row.model_id, row.currency),
            ModelSummary(row.provider, row.model_id, row.currency),
        )
        if row.is_correction:
            m.correction_effective_cost += row.effective_cost
            continue
        m.effective_cost += row.effective_cost
        if row.direction == "Input":
            m.input_tokens = _add(m.input_tokens, row.tokens)
            m.cache_labelled = m.cache_labelled or row.cache_action is not None
            if row.cache_action == "Read":
                m.cache_read_tokens = _add(m.cache_read_tokens, row.tokens)
            elif row.cache_action == "Write":
                m.cache_write_tokens = _add(m.cache_write_tokens, row.tokens)
        elif row.direction == "Output":
            m.output_tokens = _add(m.output_tokens, row.tokens)
        elif row.tokens is not None:
            m.unclassified_tokens += row.tokens

    for m in models.values():
        m.input_to_output_ratio = _ratio(m.input_tokens, m.output_tokens)
        if m.cache_labelled:  # without any label the rate is unknown, not zero
            m.cache_hit_rate = _ratio(m.cache_read_tokens or Decimal(0), m.input_tokens)
        if m.cache_read_tokens and m.input_tokens == m.cache_read_tokens:
            m.warnings.append(
                "only cache-read input rows were found; the cache hit rate is overstated if the "
                "provider does not emit a row for its other input tokens"
            )
        if m.unclassified_tokens:
            m.warnings.append(
                "some token rows carry no direction (the provider bills input and output on one "
                "meter, or did not label them) and are excluded from the ratio and the hit rate"
            )
        if m.model_id is None:
            m.warnings.append("the provider did not state a model for these rows")
    return AiTokenReport(
        rows=rows,
        models=sorted(
            models.values(), key=lambda m: (m.provider or "", m.model_id or "", m.currency)
        ),
        truncated=truncated,
        rows_without_model=sum(1 for r in rows if r.model_id is None),
        rows_without_direction=sum(1 for r in rows if r.direction is None),
        rows_with_invalid_values=invalid,
        rows_with_other_token_units=db.execute(_OTHER_UNITS, {"s": start, "e": end}).scalar() or 0,
    )
