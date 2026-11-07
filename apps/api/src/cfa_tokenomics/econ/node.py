"""A calculation node: one figure and exactly how it was produced.

Nodes form a tree (inputs are nodes). The id is a content hash, so the same inputs and formula
always give the same id, which makes results reproducible and cacheable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from .types import ZERO, Basis, BasisMix, D, canon, exact, weakest


class Status(StrEnum):
    OK = "ok"
    UNKNOWN = "unknown"  # an input is unknown; unknown is never treated as zero
    NOT_REACHED = "not_reached"  # for example payback when monthly benefit is not positive
    INFEASIBLE = "infeasible"  # for example a price for a margin that cannot be met


@dataclass(frozen=True)
class Node:
    key: str
    formula_id: str  # "input" for leaves
    formula_version: int
    value: Decimal | None
    unit: str
    currency: str | None
    mix: BasisMix
    inputs: tuple[Node, ...] = ()
    label: str = ""
    source_ref: str | None = None  # raw record, price-book entry, user assumption id
    status: Status = Status.OK
    note: str = ""
    id: str = field(init=False)

    def __post_init__(self) -> None:
        if self.value is not None and not isinstance(self.value, Decimal):
            raise TypeError("node value must be Decimal or None")
        if (self.value is None) != (self.status is not Status.OK):
            raise ValueError("value is None exactly when status is not ok")
        payload = "|".join(
            [
                self.key, self.formula_id, str(self.formula_version),
                "None" if self.value is None else canon(self.value),
                self.unit, self.currency or "", self.status.value, self.source_ref or "",
                ",".join(i.id for i in self.inputs),
                # basis and wording are part of the identity: changing "assumed" to "observed" must be
                # detectable, not just a change of number.
                *(canon(m) for m in (self.mix.observed, self.mix.estimated, self.mix.assumed)),
                self.label, self.note,
            ]
        )  # fmt: skip
        object.__setattr__(self, "id", hashlib.sha256(payload.encode()).hexdigest()[:16])

    @property
    def basis(self) -> Basis:
        return self.mix.weakest

    @property
    def known(self) -> bool:
        return self.status is Status.OK

    def walk(self):
        """Yield this node and every input beneath it (explain view)."""
        yield self
        for i in self.inputs:
            yield from i.walk()


def leaf(
    key: str,
    value: int | str | Decimal | None,
    unit: str,
    basis: Basis,
    currency: str | None = None,
    source_ref: str | None = None,
    label: str = "",
) -> Node:
    """An input. ``value=None`` means unknown, which is carried honestly and never becomes zero."""
    known = value is not None
    return Node(
        key=key, formula_id="input", formula_version=1,
        value=D(value) if known else None, unit=unit, currency=currency,
        mix=BasisMix.pure(basis), label=label, source_ref=source_ref,
        status=Status.OK if known else Status.UNKNOWN,
        note="" if known else "unknown",
    )  # fmt: skip


def _unknown_keys(inputs: list[Node]) -> list[str]:
    return [i.key for i in inputs if not i.known]


@exact
def sum_basis(inputs: list[Node]) -> BasisMix:
    """Value-weighted mix of the parts. All-zero parts fall back to the weakest basis present."""
    weights = [abs(i.value or ZERO) for i in inputs]
    total = sum(weights, ZERO)
    if total == 0:
        return BasisMix.pure(weakest([i.basis for i in inputs]))
    obs = est = asm = ZERO
    for w, i in zip(weights, inputs, strict=True):
        share = w / total
        obs += share * i.mix.observed
        est += share * i.mix.estimated
        asm += share * i.mix.assumed
    return BasisMix(obs, est, asm)


def weakest_mix(inputs: list[Node]) -> BasisMix:
    """Products and ratios take the weakest input basis (conservative)."""
    return BasisMix.pure(weakest([i.basis for i in inputs]))


def derive(
    key: str,
    formula_id: str,
    version: int,
    value: Decimal | None,
    unit: str,
    currency: str | None,
    inputs: list[Node],
    rule: str,
    note: str = "",
    status: Status = Status.OK,
    label: str = "",
) -> Node:
    """Build a derived node. Unknown inputs make the result unknown unless ``status`` says otherwise."""
    unknown = _unknown_keys(inputs)
    if unknown and status is Status.OK:
        value, status = None, Status.UNKNOWN
        note = f"unknown input: {', '.join(unknown)}"
    if status is not Status.OK:
        value = None
    mix = sum_basis(inputs) if rule == "sum" else weakest_mix(inputs)
    return Node(
        key=key, formula_id=formula_id, formula_version=version, value=value, unit=unit,
        currency=currency, mix=mix, inputs=tuple(inputs), label=label, status=status, note=note,
    )  # fmt: skip


def same_currency(inputs: list[Node]) -> str | None:
    """The single currency of the inputs; mixed currencies are refused, not summed."""
    cur = {i.currency for i in inputs if i.currency is not None}
    if len(cur) > 1:
        raise ValueError(
            f"cannot combine currencies {sorted(cur)}; convert with a dated FX rate first"
        )
    return next(iter(cur), None)
