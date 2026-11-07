"""Commercial pricing and margin (docs/economics/05-calculation-engine.md, section 9).

Marketplace fees and commitment effects are configuration (rates are inputs), never constants.
This module MODELS prices and margins; it does not invoice, bill or meter (REQ-012 clarification).
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

from .node import Node, Status, derive, same_currency
from .types import ONE, ZERO, exact


def _unit_interval(n: Node, name: str, *, upper_open: bool = False) -> None:
    if n.known:
        v = n.value  # type: ignore[assignment]
        if v < ZERO or (v >= ONE if upper_open else v > ONE):
            raise ValueError(f"{name} must be in [0, 1{')' if upper_open else ']'}")


def _guard(ins: list[Node], build) -> tuple[Decimal | None, Status, str]:
    if any(not i.known for i in ins):
        return None, Status.UNKNOWN, ""
    return build()


# ---- revenue models --------------------------------------------------------------------------------


@exact
def revenue_linear(
    key: str, quantity: Node, unit_price: Node, fixed_fee: Node | None = None
) -> Node:
    """Subscription (quantity 1), per user, per transaction, per token block, application flat fee:
    revenue = quantity x unit price (+ fixed fee)."""
    ins = [quantity, unit_price] + ([fixed_fee] if fixed_fee else [])
    cur = same_currency([unit_price] + ([fixed_fee] if fixed_fee else []))
    v = None
    if all(i.known for i in ins):
        v = quantity.value * unit_price.value + (fixed_fee.value if fixed_fee else ZERO)  # type: ignore[operator]
    return derive(key, "revenue.linear.v1", 1, v, "money", cur, ins, "product")


@exact
def revenue_usage(key: str, lines: list[tuple[Node, Node]], per: Decimal = ONE) -> Node:
    """Usage-based: sum over measures of quantity / per x price."""
    parts = [
        derive(f"{q.key}*{p.key}", "revenue.usage.line", 1,
               None if not (q.known and p.known) else q.value / per * p.value,  # type: ignore[operator]
               "money", p.currency, [q, p], "product")
        for q, p in lines
    ]  # fmt: skip
    cur = same_currency(parts)
    v = None if any(not p.known for p in parts) else sum((p.value for p in parts), ZERO)  # type: ignore[misc]
    return derive(key, "revenue.usage.v1", 1, v, "money", cur, parts, "sum")


@exact
def revenue_tiered(
    key: str, quantity: Node, tiers: list[tuple[Decimal | None, Node]], mode: str = "graduated"
) -> Node:
    """Tiered pricing. ``tiers`` is ordered (upper_bound or None for the last, unit_price).
    graduated: each tier's units are charged at that tier's price.
    volume: all units are charged at the price of the tier the total quantity falls into."""
    if mode not in ("graduated", "volume"):
        raise ValueError("mode must be graduated or volume")
    prices = [p for _, p in tiers]
    cur = same_currency(prices)
    if not (quantity.known and all(p.known for p in prices)):
        return derive(
            key, "revenue.tiered.v1", 1, None, "money", cur, [quantity, *prices], "product"
        )
    q = quantity.value  # type: ignore[assignment]
    total, lo = ZERO, ZERO
    chosen = prices[-1]
    for bound, price in tiers:
        hi = bound if bound is not None else q
        if mode == "graduated":
            total += max(min(q, hi) - lo, ZERO) * price.value  # type: ignore[operator]
        if bound is None or q <= bound:
            chosen = price
            break
        lo = bound
    if mode == "volume":
        total = q * chosen.value  # type: ignore[operator]
    return derive(
        key, f"revenue.tiered.{mode}.v1", 1, total, "money", cur, [quantity, *prices], "product"
    )


# ---- fees, margin and price ------------------------------------------------------------------------


@exact
def marketplace_fee(revenue: Node, fee_rate: Node, fixed_fee: Node | None = None) -> Node:
    """MarketplaceFee = rate x revenue + fixed fee. Rates come from a configurable fee schedule."""
    _unit_interval(fee_rate, "fee_rate", upper_open=True)
    ins = [revenue, fee_rate] + ([fixed_fee] if fixed_fee else [])
    cur = same_currency([revenue] + ([fixed_fee] if fixed_fee else []))
    v = None
    if all(i.known for i in ins):
        v = revenue.value * fee_rate.value + (fixed_fee.value if fixed_fee else ZERO)  # type: ignore[operator]
    return derive("marketplace_fee", "marketplace_fee.v1", 1, v, "money", cur, ins, "product")


@exact
def gross_margin(revenue: Node, fee: Node, cogs: Node) -> Node:
    """GrossMargin = (revenue - marketplace fee - COGS) / revenue."""
    ins = [revenue, fee, cogs]
    same_currency(ins)  # refuses mixed currencies
    status, note, v = Status.OK, "", None
    if all(i.known for i in ins):
        if revenue.value <= 0:  # type: ignore[operator]
            status, note = Status.INFEASIBLE, "revenue must be positive"
        else:
            v = (revenue.value - fee.value - cogs.value) / revenue.value  # type: ignore[operator]
    return derive(
        "gross_margin", "gross_margin.v1", 1, v, "ratio", None, ins, "ratio", note, status
    )


@exact
def required_price(
    cogs: Node, fee_rate: Node, target_margin: Node, fixed_fee: Node | None = None
) -> Node:
    """Price such that (P x (1 - f) - fixed - COGS) / P = m, i.e. P = (COGS + fixed) / (1 - f - m).
    Infeasible when 1 - f - m <= 0: the margin cannot be met at any price."""
    _unit_interval(fee_rate, "fee_rate", upper_open=True)
    _unit_interval(target_margin, "target_margin", upper_open=True)
    ins = [cogs, fee_rate, target_margin] + ([fixed_fee] if fixed_fee else [])
    cur = same_currency([cogs] + ([fixed_fee] if fixed_fee else []))
    status, note, v = Status.OK, "", None
    if all(i.known for i in ins):
        denom = ONE - fee_rate.value - target_margin.value  # type: ignore[operator]
        if denom <= 0:
            status, note = Status.INFEASIBLE, "fee rate plus target margin must be below 100%"
        else:
            v = (cogs.value + (fixed_fee.value if fixed_fee else ZERO)) / denom  # type: ignore[operator]
    return derive(
        "required_price", "required_price.v1", 1, v, "money", cur, ins, "ratio", note, status
    )


@exact
def required_unit_price(
    variable_unit_cost: Node, fixed_cost: Node, volume: Node, fee_rate: Node, target_margin: Node
) -> Node:
    """UnitPrice = (variable unit cost + fixed cost / volume) / (1 - f - m)."""
    _unit_interval(fee_rate, "fee_rate", upper_open=True)
    _unit_interval(target_margin, "target_margin", upper_open=True)
    ins = [variable_unit_cost, fixed_cost, volume, fee_rate, target_margin]
    cur = same_currency([variable_unit_cost, fixed_cost])
    status, note, v = Status.OK, "", None
    if all(i.known for i in ins):
        denom = ONE - fee_rate.value - target_margin.value  # type: ignore[operator]
        if volume.value <= 0:  # type: ignore[operator]
            status, note = Status.INFEASIBLE, "volume must be positive"
        elif denom <= 0:
            status, note = Status.INFEASIBLE, "fee rate plus target margin must be below 100%"
        else:
            v = (variable_unit_cost.value + fixed_cost.value / volume.value) / denom  # type: ignore[operator]
    return derive(
        "required_unit_price",
        "required_unit_price.v1",
        1,
        v,
        "money/unit",
        cur,
        ins,
        "ratio",
        note,
        status,
    )


@exact
def break_even_volume(
    fixed_cost: Node, unit_price: Node, variable_unit_cost: Node, fee_rate: Node
) -> Node:
    """N* = fixed / (price x (1 - f) - variable unit cost). Infeasible if each unit loses money."""
    _unit_interval(fee_rate, "fee_rate", upper_open=True)
    ins = [fixed_cost, unit_price, variable_unit_cost, fee_rate]
    status, note, v = Status.OK, "", None
    if all(i.known for i in ins):
        contribution = unit_price.value * (ONE - fee_rate.value) - variable_unit_cost.value  # type: ignore[operator]
        if contribution <= 0:
            status, note = Status.INFEASIBLE, "unit contribution is not positive"
        else:
            v = fixed_cost.value / contribution  # type: ignore[operator]
    return derive(
        "break_even_volume", "break_even.v1", 1, v, "units", None, ins, "ratio", note, status
    )


# ---- commitments -----------------------------------------------------------------------------------


@exact
def committed_spend(commit: Node, usage_at_commit_rate: Node, overage_factor: Node) -> Node:
    """Spend under a commitment = commit + max(0, usage - commit) x overage factor (1 = same rate)."""
    ins = [commit, usage_at_commit_rate, overage_factor]
    cur = same_currency([commit, usage_at_commit_rate])
    v = None
    if all(i.known for i in ins):
        v = (
            commit.value
            + max(usage_at_commit_rate.value - commit.value, ZERO) * overage_factor.value
        )  # type: ignore[operator]
    return derive("committed_spend", "committed_spend.v1", 1, v, "money", cur, ins, "sum")


@exact
def commitment_waste(commit: Node, usage_at_commit_rate: Node) -> Node:
    """Unused commitment = max(0, commit - usage)."""
    ins = [commit, usage_at_commit_rate]
    cur = same_currency(ins)
    v = (
        None
        if any(not i.known for i in ins)
        else max(commit.value - usage_at_commit_rate.value, ZERO)
    )  # type: ignore[operator]
    return derive("commitment_waste", "commitment_waste.v1", 1, v, "money", cur, ins, "sum")


def ceil_div(a: Decimal, b: Decimal) -> Decimal:
    """Ceiling of a / b for a step-cost function."""
    return (a / b).to_integral_value(rounding=ROUND_CEILING)
