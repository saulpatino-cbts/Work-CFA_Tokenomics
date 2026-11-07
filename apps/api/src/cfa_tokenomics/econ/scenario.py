"""Driver-based scenario evaluation and sensitivity (docs/economics/05-calculation-engine.md, section 8).

A scenario is a set of inputs. ``evaluate`` turns them into the full chain: tokens, AI cost, infrastructure,
total cost, unit cost, value, ROI, payback, required price and margin, as traceable nodes. Scenarios of every
kind (baseline, current, forecast, optimized, customer proposal) use this same function, so "current" and
"forecast" can never use different arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from . import commercial as com
from . import formulas as f
from .node import Node, derive, leaf, same_currency
from .types import ONE, Basis, exact

CATEGORIES = ("input", "output", "cache_read", "cache_write", "reasoning")


@dataclass(frozen=True)
class ModelLine:
    """A model in the mix: its share of token volume and its price per million tokens by category."""

    name: str
    share: Node
    prices: dict[str, Node]


@dataclass(frozen=True)
class ScenarioInputs:
    currency: str
    # consumption drivers
    users: Node
    adoption: Node  # share of users actively using the application, 0..1
    interactions_per_user: Node  # per active user per month
    tokens_per_interaction: dict[str, Node]
    models: tuple[ModelLine, ...]
    transactions_per_user: Node  # business transactions per user per month
    # cost
    infra_fixed: Node
    supporting_api: Node
    licence: Node
    ops_hours: Node
    ops_rate: Node
    dev_investment: Node
    dev_months: Node
    infra_variable_per_interaction: Node | None = None
    infra_step: tuple[Node, Node] | None = None  # (interactions per step, cost per step)
    # value
    baseline_hours_per_txn: Node | None = None
    assisted_hours_per_txn: Node | None = None
    loaded_rate: Node | None = None
    realization: Node | None = None
    cashability: Node | None = None
    error_value: Node | None = None  # None means "not modelled", which differs from unknown
    revenue_value: Node | None = None
    avoided_cost: Node | None = None
    # commercial
    target_margin: Node | None = None
    marketplace_fee_rate: Node | None = None
    marketplace_fixed_fee: Node | None = None
    price: Node | None = None


def _mul(key: str, fid: str, a: Node, b: Node, unit: str, currency: str | None = None) -> Node:
    v = None if not (a.known and b.known) else a.value * b.value  # type: ignore[operator]
    return derive(key, fid, 1, v, unit, currency, [a, b], "product")


@exact
def evaluate(i: ScenarioInputs) -> dict[str, Node]:
    out: dict[str, Node] = {}
    shares = [m.share for m in i.models]
    if all(s.known for s in shares) and abs(sum(s.value for s in shares) - ONE) > Decimal("1e-12"):  # type: ignore[misc]
        raise ValueError("model shares must sum to 1")

    out["active_users"] = _mul("active_users", "active_users.v1", i.users, i.adoption, "users")
    out["interactions"] = _mul(
        "interactions",
        "interactions.v1",
        out["active_users"],
        i.interactions_per_user,
        "interactions",
    )
    for cat, per_int in i.tokens_per_interaction.items():
        out[f"tokens.{cat}"] = _mul(
            f"tokens.{cat}", "tokens.v1", out["interactions"], per_int, "tokens"
        )

    lines: list[tuple[Node, Node]] = []
    for m in i.models:
        for cat in i.tokens_per_interaction:
            if cat not in m.prices:
                raise ValueError(
                    f"model {m.name} has no price for {cat}; a missing price is not zero"
                )
            qty = _mul(
                f"{m.name}.{cat}.tokens", "model_tokens.v1", out[f"tokens.{cat}"], m.share, "tokens"
            )
            lines.append((qty, m.prices[cat]))
    out["ai_cost"] = f.ai_cost_estimate(lines)

    infra_parts = [i.infra_fixed]
    if i.infra_variable_per_interaction is not None:
        infra_parts.append(
            _mul(
                "infra_variable",
                "infra_variable.v1",
                out["interactions"],
                i.infra_variable_per_interaction,
                "money",
                i.currency,
            )
        )
    if i.infra_step is not None:
        cap, cost = i.infra_step
        steps = derive(
            "infra_steps",
            "infra_steps.v1",
            1,
            None
            if not (out["interactions"].known and cap.known)
            else com.ceil_div(out["interactions"].value, cap.value),
            "steps",
            None,
            [out["interactions"], cap],
            "ratio",
        )  # type: ignore[arg-type]
        infra_parts.append(
            _mul("infra_step_cost", "infra_step_cost.v1", steps, cost, "money", i.currency)
        )
    out["infra_cost"] = f.total("infra_cost", "infra_cost.v1", 1, infra_parts)
    out["ops_cost"] = f.ops_cost(i.ops_hours, i.ops_rate)
    out["dev_cost"] = f.dev_amortization(i.dev_investment, i.dev_months)
    out["tca"] = f.tca(
        out["ai_cost"],
        out["infra_cost"],
        i.supporting_api,
        i.licence,
        out["ops_cost"],
        out["dev_cost"],
    )
    out["run_cost"] = f.run_cost(
        out["ai_cost"], out["infra_cost"], i.supporting_api, i.licence, out["ops_cost"]
    )

    out["transactions"] = _mul(
        "transactions", "transactions.v1", i.users, i.transactions_per_user, "transactions"
    )
    out["cost_per_interaction"] = f.unit_cost(out["tca"], out["interactions"], "interaction")
    out["cost_per_active_user"] = f.unit_cost(out["tca"], out["active_users"], "active_user")
    out["cost_per_transaction"] = f.unit_cost(out["tca"], out["transactions"], "transaction")
    out["run_cost_per_interaction"] = f.unit_cost(
        out["run_cost"], out["interactions"], "interaction"
    )

    value_inputs = (
        i.baseline_hours_per_txn,
        i.assisted_hours_per_txn,
        i.loaded_rate,
        i.realization,
        i.cashability,
    )
    if all(v is not None for v in value_inputs):
        hours = f.hours_saved(
            i.baseline_hours_per_txn,
            i.assisted_hours_per_txn,
            out["transactions"],
            i.adoption,
            i.realization,
        )  # type: ignore[arg-type]
        out["hours_saved"] = hours
        cap = f.labor_value(hours, i.loaded_rate)  # type: ignore[arg-type]
        out["labor_value_capacity"] = cap
        out["labor_value_cashable"] = f.cashable_value(cap, i.cashability)  # type: ignore[arg-type]
        others = [n for n in (i.error_value, i.revenue_value, i.avoided_cost) if n is not None]
        for tag in ("capacity", "cashable"):
            bv = f.business_value([out[f"labor_value_{tag}"], *others], key=f"business_value_{tag}")
            out[f"business_value_{tag}"] = bv
            net = f.net_value(bv, out["tca"])
            out[f"net_value_{tag}"] = net
            out[f"roi_{tag}"] = f.roi(net, out["tca"])
            out[f"payback_{tag}"] = f.payback_months(i.dev_investment, bv, out["run_cost"])

    if i.target_margin is not None and i.marketplace_fee_rate is not None:
        out["required_price"] = com.required_price(
            out["run_cost"], i.marketplace_fee_rate, i.target_margin, i.marketplace_fixed_fee
        )
    if i.price is not None and i.marketplace_fee_rate is not None:
        same_currency([i.price, out["run_cost"]])
        fee = com.marketplace_fee(i.price, i.marketplace_fee_rate, i.marketplace_fixed_fee)
        out["marketplace_fee"] = fee
        out["gross_margin"] = com.gross_margin(i.price, fee, out["run_cost"])
    return out


# ---- sensitivity -----------------------------------------------------------------------------------


def with_value(inputs: ScenarioInputs, path: str, value: int | str | Decimal) -> ScenarioInputs:
    """Return inputs with the node at ``path`` replaced by a hypothetical value (basis: assumed).

    Paths: ``users``, ``tokens_per_interaction.input``, ``models.0.prices.input``, ``models.0.share``."""

    def swap(obj: Any, parts: list[str]) -> Any:
        head, rest = parts[0], parts[1:]
        if isinstance(obj, dict):
            cur = obj[head]
            return {**obj, head: swap(cur, rest) if rest else _hypo(cur, value)}
        if isinstance(obj, tuple) and head.isdigit():
            idx = int(head)
            new = swap(obj[idx], rest) if rest else _hypo(obj[idx], value)
            return obj[:idx] + (new,) + obj[idx + 1 :]
        cur = getattr(obj, head)
        return replace(obj, **{head: swap(cur, rest) if rest else _hypo(cur, value)})

    return swap(inputs, path.split("."))


def _hypo(old: Any, value: int | str | Decimal) -> Node:
    if not isinstance(old, Node):
        raise TypeError("path must end at a Node")
    return leaf(
        old.key,
        value,
        old.unit,
        Basis.ASSUMED,
        old.currency,
        source_ref=f"sensitivity of {old.id}",
        label=old.label,
    )


def tornado(
    inputs: ScenarioInputs,
    ranges: dict[str, tuple[int | str | Decimal, int | str | Decimal]],
    output: str,
) -> list[dict[str, Any]]:
    """One-at-a-time sensitivity. Each driver is moved to its low then high value; rows are ordered by the
    swing in ``output``. Only the named drivers move; observed inputs never get uncertainty ranges."""
    base = evaluate(inputs)[output]
    rows: list[dict[str, Any]] = []
    for path, (lo, hi) in ranges.items():
        r_lo = evaluate(with_value(inputs, path, lo))[output]
        r_hi = evaluate(with_value(inputs, path, hi))[output]
        swing = abs(r_hi.value - r_lo.value) if r_lo.known and r_hi.known else None  # type: ignore[operator]
        rows.append({"path": path, "low": r_lo, "high": r_hi, "swing": swing, "base": base})
    rows.sort(key=lambda r: (r["swing"] is None, -(r["swing"] or 0)))
    return rows


def grid(
    inputs: ScenarioInputs, x_path: str, xs: list[Any], y_path: str, ys: list[Any], output: str
) -> list[list[Node]]:
    """Two-way sensitivity: output for every (x, y) pair."""
    return [
        [evaluate(with_value(with_value(inputs, x_path, x), y_path, y))[output] for x in xs]
        for y in ys
    ]
