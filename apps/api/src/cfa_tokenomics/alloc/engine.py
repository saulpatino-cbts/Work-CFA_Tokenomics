"""Pure allocation engine. No database, clock or randomness.

A cost line is split among applications by the first rule that matches and can be applied. The split is
exact: for every amount, the slices add up to the original to the last decimal place (largest-remainder
rounding, ties broken by position), and whatever no rule could place goes to an explicit "unallocated"
slice with a reason. Nothing is dropped and nothing is guessed: a rule that matches but cannot be applied
(a missing tag, an unmapped value, a missing driver) falls through to the next rule.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from typing import Any

SCALE = 18
UNIT = 10**SCALE
MEASURES = ("billed", "effective", "list", "contracted")
METHODS = ("direct", "tag", "fixed_percent", "even", "proportional")
OPS = ("eq", "prefix", "in", "exists", "not_exists")
FIELDS = (
    "service_name", "service_category", "service_subcategory", "service_provider_name",
    "host_provider_name", "invoice_issuer_name", "resource_id", "resource_name", "resource_type",
    "sub_account_id", "billing_account_id", "region_id", "sku_id", "charge_category", "charge_class",
    "pricing_category", "commitment_discount_id", "billing_currency", "allocated_method_id",
    "allocated_resource_id",
)  # fmt: skip


def to_units(d: Decimal) -> int:
    """Exact integer count of 10^-18 units. Refuses a value with finer precision (never rounds).

    Uses the digit tuple and integer arithmetic only: Decimal arithmetic such as ``scaleb`` rounds to
    the ambient context precision (28 digits by default), which would corrupt 38-digit amounts."""
    sign, digits, exp = d.as_tuple()
    if not isinstance(exp, int):
        raise ValueError("amount must be finite")
    n = int("".join(map(str, digits)) or "0")
    shift = exp + SCALE
    if shift >= 0:
        n *= 10**shift
    else:
        n, remainder = divmod(n, 10 ** (-shift))
        if remainder:
            raise ValueError("amount has more than 18 decimal places")
    return -n if sign else n


def from_units(n: int) -> Decimal:
    """The Decimal for ``n`` units. The string constructor is exact; it never rounds."""
    return Decimal(f"{n}E-{SCALE}")


def split_exact(amount: Decimal, weights: list[Fraction]) -> list[Decimal]:
    """Split ``amount`` in proportion to ``weights`` so the parts sum to it exactly.

    Largest-remainder method on integer units; remainders are handed out by largest fractional part and
    then by lowest index, so the result is deterministic. Negative amounts (credits) split the same way."""
    if not weights or any(w < 0 for w in weights) or sum(weights) <= 0:
        raise ValueError("weights must be non-negative with a positive total")
    total = abs(to_units(amount))
    wsum = sum(weights)
    ideal = [Fraction(total) * w / wsum for w in weights]
    parts = [int(x) for x in ideal]  # floor (values are non-negative)
    leftover = total - sum(parts)
    order = sorted(range(len(parts)), key=lambda i: (-(ideal[i] - parts[i]), i))
    for i in order[:leftover]:
        parts[i] += 1
    sign = -1 if amount < 0 else 1
    return [from_units(sign * p) for p in parts]


def _tag_text(raw: Any) -> str | None:
    """Tag value as text. FOCUS stores a value-less tag as boolean true; it exists but has no value."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return "true" if raw else "false"
    return str(raw)


@dataclass(frozen=True)
class Condition:
    field: str  # a column name, or "tag:<key>"
    op: str
    value: Any = None

    def matches(self, fields: dict[str, str | None], tags: dict[str, Any]) -> bool:
        if self.field.startswith("tag:"):
            actual = _tag_text(tags.get(self.field[4:]))
        else:
            actual = fields.get(self.field)
        if self.op == "exists":
            return actual is not None
        if self.op == "not_exists":
            return actual is None
        if actual is None:
            return False
        if self.op == "eq":
            return actual == self.value
        if self.op == "prefix":
            return actual.startswith(str(self.value))
        return actual in self.value  # "in"


@dataclass(frozen=True)
class Rule:
    key: str
    version: int
    priority: int
    method: str
    conditions: tuple[Condition, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CostLine:
    id: uuid.UUID
    amounts: dict[str, Decimal]  # keys are MEASURES
    fields: dict[str, str | None]
    tags: dict[str, Any]
    charge_period_start: datetime


@dataclass(frozen=True)
class Slice:
    application_id: uuid.UUID | None  # None is the explicit unallocated bucket
    workload_id: uuid.UUID | None
    rule_key: str | None
    rule_version: int | None
    method: str  # a rule method, or "unallocated"
    reason: str | None  # why it is unallocated, or why a percent remainder exists
    share: Decimal  # for display; the amounts are authoritative
    amounts: dict[str, Decimal]


@dataclass
class Context:
    apps_by_name: dict[str, uuid.UUID] = field(default_factory=dict)
    # (rule key, application id) -> [(period_start, period_end, version, value)]
    drivers: dict[tuple[str, uuid.UUID], list[tuple[datetime, datetime, int, Decimal]]] = field(
        default_factory=dict
    )


def validate_rule(
    method: str, params: dict[str, Any], conditions: list[Condition] | tuple[Condition, ...]
) -> None:
    """Refuse a malformed rule when it is created, not when it first misfires."""
    if method not in METHODS:
        raise ValueError(f"method must be one of {', '.join(METHODS)}")
    for c in conditions:
        if c.op not in OPS:
            raise ValueError(f"unknown condition operator {c.op!r}")
        if not (c.field in FIELDS or (c.field.startswith("tag:") and len(c.field) > 4)):
            raise ValueError(f"unknown condition field {c.field!r}")
        if c.op in ("eq", "prefix") and not isinstance(c.value, str):
            raise ValueError("eq and prefix need a text value")
        if c.op == "in" and not (isinstance(c.value, (list, tuple)) and c.value):
            raise ValueError("in needs a non-empty list")
    if method == "direct":
        _uuid(params.get("application_id"))
    elif method == "tag":
        if not isinstance(params.get("tag_key"), str) or not params["tag_key"]:
            raise ValueError("tag rules need a tag_key")
        for v in (params.get("map") or {}).values():
            _uuid(v)
    elif method == "fixed_percent":
        targets = params.get("targets")
        if not targets:
            raise ValueError("fixed_percent needs targets")
        ids = [_uuid(t.get("application_id")) for t in targets]
        if len(set(ids)) != len(ids):
            raise ValueError("an application appears twice")
        pcts = [Decimal(str(t.get("percent"))) for t in targets]
        if any(p <= 0 or p > 100 for p in pcts) or sum(pcts) > 100:
            raise ValueError("percentages must be positive and total at most 100")
    else:  # even, proportional
        ids = [_uuid(a) for a in params.get("application_ids") or []]
        if len(ids) < 2 and method == "even":
            raise ValueError("even needs at least two applications")
        if not ids:
            raise ValueError(f"{method} needs application_ids")
        if len(set(ids)) != len(ids):
            raise ValueError("an application appears twice")


def _uuid(v: Any) -> uuid.UUID:
    try:
        return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))
    except (ValueError, AttributeError, TypeError):
        raise ValueError("expected an application id") from None


def _driver_value(ctx: Context, rule: Rule, app: uuid.UUID, at: datetime) -> Decimal | None:
    rows = [r for r in ctx.drivers.get((rule.key, app), []) if r[0] <= at < r[1]]
    return max(rows, key=lambda r: r[2])[3] if rows else None


def _targets(rule: Rule, line: CostLine, ctx: Context):
    """Return (list of (application_id, workload_id, weight), remainder_weight) or (None, reason)."""
    p = rule.params
    if rule.method == "direct":
        wl = p.get("workload_id")
        return [(_uuid(p["application_id"]), _uuid(wl) if wl else None, Fraction(1))], Fraction(0)
    if rule.method == "tag":
        raw = line.tags.get(p["tag_key"])
        if raw is None:
            return None, "tag_missing"
        if isinstance(raw, bool):  # FOCUS: a tag key without a value holds boolean true
            return None, "tag_without_value"
        value = str(raw)
        target = (p.get("map") or {}).get(value)
        app = _uuid(target) if target else ctx.apps_by_name.get(value)
        if app is None:
            return None, "tag_unmapped"
        return [(app, None, Fraction(1))], Fraction(0)
    if rule.method == "fixed_percent":
        items = [
            (_uuid(t["application_id"]), None, Fraction(Decimal(str(t["percent"]))) / 100)
            for t in p["targets"]
        ]
        return items, Fraction(1) - sum(w for _, _, w in items)
    apps = [_uuid(a) for a in p["application_ids"]]
    if rule.method == "even":
        return [(a, None, Fraction(1)) for a in apps], Fraction(0)
    values = [_driver_value(ctx, rule, a, line.charge_period_start) for a in apps]  # proportional
    if any(v is None for v in values):
        return None, "driver_missing"
    if sum(values) <= 0:  # type: ignore[arg-type]
        return None, "driver_zero"
    return [(a, None, Fraction(v)) for a, v in zip(apps, values, strict=True)], Fraction(0)  # type: ignore[arg-type]


def allocate_line(line: CostLine, rules: list[Rule], ctx: Context) -> list[Slice]:
    """Split one cost line. The first matching rule that can be applied wins."""
    first_reason: str | None = None
    for rule in sorted(rules, key=lambda r: (r.priority, r.key)):
        if not all(c.matches(line.fields, line.tags) for c in rule.conditions):
            continue
        targets, extra = _targets(rule, line, ctx)
        if targets is None:
            first_reason = first_reason or extra  # type: ignore[assignment]
            continue
        entries: list[tuple[uuid.UUID | None, uuid.UUID | None, Fraction, str | None]] = [
            (a, w, wt, None) for a, w, wt in targets
        ]
        if extra > 0:
            entries.append((None, None, extra, "percent_remainder"))
        return _build(line, entries, rule)
    return _build(line, [(None, None, Fraction(1), first_reason or "no_rule")], None)


def _build(line: CostLine, entries, rule: Rule | None) -> list[Slice]:
    weights = [e[2] for e in entries]
    wsum = sum(weights)
    per_measure = {m: split_exact(line.amounts[m], weights) for m in MEASURES}
    out = []
    for i, (app, wl, wt, reason) in enumerate(entries):
        unallocated = app is None
        out.append(
            Slice(
                application_id=app, workload_id=wl,
                rule_key=None if (rule is None) else rule.key,
                rule_version=None if (rule is None) else rule.version,
                method="unallocated" if unallocated else rule.method,  # type: ignore[union-attr]
                reason=reason,
                share=Decimal(wt.numerator) / Decimal(wt.denominator) / (Decimal(wsum.numerator) / Decimal(wsum.denominator)),
                amounts={m: per_measure[m][i] for m in MEASURES},
            )
        )  # fmt: skip
    return out
