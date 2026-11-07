"""Cost, value, ROI and unit-economics formulas (docs/economics/05-calculation-engine.md, sections 1 to 7).

Every function returns a ``Node`` carrying its formula id, version and inputs. Unknown inputs give an
unknown result. Money is Decimal with a currency; mixed currencies are refused.
"""

from __future__ import annotations

from decimal import Decimal

from .node import Node, Status, derive, same_currency
from .types import ONE, ZERO, D, exact

MILLION = D(1_000_000)


@exact
def ai_cost_estimate(
    lines: list[tuple[Node, Node]], per: Decimal = MILLION, key: str = "ai_cost"
) -> Node:
    """Estimated AI cost: sum of quantity x price. Prices come from a price book, so the result is
    ``estimated`` even when the quantities are observed. ``per`` is the quantity the price is quoted for
    (for example 1,000,000 tokens)."""
    parts: list[Node] = []
    for qty, price in lines:
        cur = same_currency([price])
        v = None if not (qty.known and price.known) else qty.value / per * price.value  # type: ignore[operator]
        parts.append(
            derive(f"{qty.key}*{price.key}", "ai_cost.line", 1, v, price.unit.split("/")[0], cur,
                   [qty, price], "product")
        )  # fmt: skip
    return total(key, "ai_cost.est", 1, parts)


@exact
def total(key: str, formula_id: str, version: int, parts: list[Node], label: str = "") -> Node:
    """Sum of money parts. Any unknown part makes the total unknown (no silent understatement)."""
    cur = same_currency(parts)
    value = None if any(not p.known for p in parts) else sum((p.value for p in parts), ZERO)  # type: ignore[misc]
    return derive(
        key,
        formula_id,
        version,
        value,
        parts[0].unit if parts else "",
        cur,
        list(parts),
        "sum",
        label=label,
    )


@exact
def ops_cost(hours: Node, rate: Node) -> Node:
    v = None if not (hours.known and rate.known) else hours.value * rate.value  # type: ignore[operator]
    return derive("ops_cost", "ops.v1", 1, v, "money", rate.currency, [hours, rate], "product")


@exact
def dev_amortization(investment: Node, months: Node) -> Node:
    """Straight-line amortization of the build cost over ``months``."""
    if investment.known and months.known and months.value <= 0:  # type: ignore[operator]
        raise ValueError("amortization months must be positive")
    v = None if not (investment.known and months.known) else investment.value / months.value  # type: ignore[operator]
    return derive(
        "dev_cost",
        "dev_amortization.v1",
        1,
        v,
        "money/month",
        investment.currency,
        [investment, months],
        "product",
    )


@exact
def tca(ai: Node, infra: Node, supporting: Node, licence: Node, ops: Node, dev: Node) -> Node:
    """Total Cost of Application for a period."""
    return total("tca", "tca.v1", 1, [ai, infra, supporting, licence, ops, dev])


@exact
def run_cost(ai: Node, infra: Node, supporting: Node, licence: Node, ops: Node) -> Node:
    """Operating cost: TCA without amortized development. Used for payback and COGS."""
    return total("run_cost", "run_cost.v1", 1, [ai, infra, supporting, licence, ops])


@exact
def unit_cost(cost: Node, units: Node, unit_name: str) -> Node:
    """Cost per unit (transaction, interaction, user, customer, outcome)."""
    status, note, v = Status.OK, "", None
    if cost.known and units.known:
        if units.value <= 0:  # type: ignore[operator]
            status, note = Status.INFEASIBLE, "no units"
        else:
            v = cost.value / units.value  # type: ignore[operator]
    return derive(
        f"cost_per_{unit_name}",
        "unit_cost.v1",
        1,
        v,
        f"money/{unit_name}",
        cost.currency,
        [cost, units],
        "ratio",
        note,
        status,
    )


# ---- business value --------------------------------------------------------------------------------


@exact
def hours_saved(
    base_hours_per_txn: Node,
    assisted_hours_per_txn: Node,
    transactions: Node,
    adoption: Node,
    realization: Node,
) -> Node:
    """HoursSaved = (baseline - assisted) x transactions x adoption x realization. Adoption and realization are
    explicit assumptions in [0, 1]; they are never hidden defaults."""
    for n in (adoption, realization):
        if n.known and not (ZERO <= n.value <= ONE):  # type: ignore[operator]
            raise ValueError(f"{n.key} must be between 0 and 1")
    ins = [base_hours_per_txn, assisted_hours_per_txn, transactions, adoption, realization]
    v = (
        None
        if any(not i.known for i in ins)
        else (base_hours_per_txn.value - assisted_hours_per_txn.value)
        * transactions.value
        * adoption.value
        * realization.value
    )  # type: ignore[operator]
    return derive("hours_saved", "hours_saved.v1", 1, v, "hours", None, ins, "product")


@exact
def labor_value(hours: Node, loaded_rate: Node) -> Node:
    v = None if not (hours.known and loaded_rate.known) else hours.value * loaded_rate.value  # type: ignore[operator]
    return derive(
        "labor_value",
        "labor_value.v1",
        1,
        v,
        "money",
        loaded_rate.currency,
        [hours, loaded_rate],
        "product",
    )


@exact
def cashable_value(capacity: Node, cashability: Node) -> Node:
    """Capacity value only becomes cash if headcount or spend changes; cashability is an explicit assumption."""
    if cashability.known and not (ZERO <= cashability.value <= ONE):  # type: ignore[operator]
        raise ValueError("cashability must be between 0 and 1")
    v = None if not (capacity.known and cashability.known) else capacity.value * cashability.value  # type: ignore[operator]
    return derive(
        "cashable_value",
        "cashable_value.v1",
        1,
        v,
        "money",
        capacity.currency,
        [capacity, cashability],
        "product",
    )


@exact
def loaded_rate(annual_salary: Node, burden_rate: Node, productive_hours_per_year: Node) -> Node:
    """LoadedRate = salary x (1 + burden) / productive hours."""
    ins = [annual_salary, burden_rate, productive_hours_per_year]
    if productive_hours_per_year.known and productive_hours_per_year.value <= 0:  # type: ignore[operator]
        raise ValueError("productive hours must be positive")
    v = (
        None
        if any(not i.known for i in ins)
        else annual_salary.value * (ONE + burden_rate.value) / productive_hours_per_year.value
    )  # type: ignore[operator]
    return derive(
        "loaded_rate", "loaded_rate.v1", 1, v, "money/hour", annual_salary.currency, ins, "product"
    )


@exact
def error_value(base_errors: Node, assisted_errors: Node, cost_per_error: Node) -> Node:
    ins = [base_errors, assisted_errors, cost_per_error]
    v = (
        None
        if any(not i.known for i in ins)
        else (base_errors.value - assisted_errors.value) * cost_per_error.value
    )  # type: ignore[operator]
    return derive(
        "error_value", "error_value.v1", 1, v, "money", cost_per_error.currency, ins, "product"
    )


@exact
def revenue_value(uplift: Node, contribution_margin: Node) -> Node:
    """Revenue value counts contribution margin, not gross revenue."""
    if contribution_margin.known and not (ZERO <= contribution_margin.value <= ONE):  # type: ignore[operator]
        raise ValueError("contribution margin must be between 0 and 1")
    v = (
        None
        if not (uplift.known and contribution_margin.known)
        else uplift.value * contribution_margin.value
    )  # type: ignore[operator]
    return derive(
        "revenue_value",
        "revenue_value.v1",
        1,
        v,
        "money",
        uplift.currency,
        [uplift, contribution_margin],
        "product",
    )


@exact
def business_value(components: list[Node], key: str = "business_value") -> Node:
    return total(key, "business_value.v1", 1, components)


# ---- ROI and payback --------------------------------------------------------------------------------


@exact
def net_value(value: Node, cost: Node) -> Node:
    cur = same_currency([value, cost])
    v = None if not (value.known and cost.known) else value.value - cost.value  # type: ignore[operator]
    return derive("net_value", "net_value.v1", 1, v, "money", cur, [value, cost], "sum")


@exact
def roi(net: Node, cost: Node) -> Node:
    """ROI = net value / total cost of application."""
    status, note, v = Status.OK, "", None
    if net.known and cost.known:
        if cost.value <= 0:  # type: ignore[operator]
            status, note = Status.INFEASIBLE, "cost must be positive"
        else:
            v = net.value / cost.value  # type: ignore[operator]
    return derive("roi", "roi.v1", 1, v, "ratio", None, [net, cost], "ratio", note, status)


@exact
def payback_months(investment: Node, monthly_value: Node, monthly_run_cost: Node) -> Node:
    """Payback = investment / (monthly value - monthly RUN cost). Run cost, not TCA: TCA already contains the
    amortized investment and would count it twice. Reported as not reached when the benefit is not positive."""
    ins = [investment, monthly_value, monthly_run_cost]
    status, note, v = Status.OK, "", None
    if all(i.known for i in ins):
        benefit = monthly_value.value - monthly_run_cost.value  # type: ignore[operator]
        if benefit <= 0:
            status, note = Status.NOT_REACHED, "monthly net benefit is not positive"
        else:
            v = investment.value / benefit  # type: ignore[operator]
    return derive("payback_months", "payback.v1", 1, v, "months", None, ins, "ratio", note, status)
