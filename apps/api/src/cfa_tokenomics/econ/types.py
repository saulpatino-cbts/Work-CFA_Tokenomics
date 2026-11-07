"""Exact numbers and the basis of a figure."""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from enum import StrEnum
from typing import Any

CTX = Context(prec=34, rounding=ROUND_HALF_EVEN)
ZERO = Decimal(0)
ONE = Decimal(1)
_TOL = Decimal("1e-20")


def exact[F: Callable[..., Any]](fn: F) -> F:
    """Run ``fn`` under the library's decimal context, never the process-global one."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with localcontext(CTX):
            return fn(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def D(x: int | str | Decimal) -> Decimal:
    """Build a Decimal. Floats are refused: binary floating point is not allowed for money or quantity."""
    if isinstance(x, bool) or isinstance(x, float):
        raise TypeError(f"refusing {type(x).__name__}; use int, str or Decimal")
    return Decimal(x)


class Basis(StrEnum):
    """Where a figure comes from. Never inferred silently."""

    OBSERVED = "observed"  # reported by a source
    ESTIMATED = "estimated"  # computed by the product from stated inputs and method
    ASSUMED = "assumed"  # entered by a user


_RANK = {Basis.OBSERVED: 0, Basis.ESTIMATED: 1, Basis.ASSUMED: 2}


def weakest(bases: list[Basis]) -> Basis:
    return max(bases, key=_RANK.__getitem__)


@dataclass(frozen=True)
class BasisMix:
    """Share of a figure that rests on each basis. Shares sum to one."""

    observed: Decimal = ZERO
    estimated: Decimal = ZERO
    assumed: Decimal = ZERO

    def __post_init__(self) -> None:
        if abs(self.observed + self.estimated + self.assumed - ONE) > _TOL * 1000:
            raise ValueError("basis shares must sum to 1")

    @staticmethod
    def pure(basis: Basis) -> BasisMix:
        return BasisMix(
            observed=ONE if basis is Basis.OBSERVED else ZERO,
            estimated=ONE if basis is Basis.ESTIMATED else ZERO,
            assumed=ONE if basis is Basis.ASSUMED else ZERO,
        )

    @property
    def weakest(self) -> Basis:
        if self.assumed > 0:
            return Basis.ASSUMED
        if self.estimated > 0:
            return Basis.ESTIMATED
        return Basis.OBSERVED

    @property
    def assumption_dependent(self) -> bool:
        return self.assumed > 0
