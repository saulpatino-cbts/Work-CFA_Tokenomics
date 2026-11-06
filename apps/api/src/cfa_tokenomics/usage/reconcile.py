"""Reconcile request observations with a provider aggregate (ADR 0007).

The two sources are never added. See docs/token-accounting.md.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from .models import RequestObservation


class Status(StrEnum):
    APP_ONLY = "app_only"
    PROVIDER_ONLY = "provider_only"
    RECONCILED = "reconciled"
    APP_EXCEEDS_PROVIDER = "app_exceeds_provider"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Reconciled:
    category: str
    status: Status
    app_observed: int | None  # sum of known request values, None if none known
    provider_reported: float | None
    total: float | None
    unattributed: float | None  # provider traffic the app did not route
    partial: bool  # some request rows lacked this category


def app_sum(observations: Iterable[RequestObservation], category: str) -> tuple[int | None, bool]:
    """Sum known values only. Returns (sum or None, partial)."""
    values = [getattr(o, category) for o in observations]
    known = [v for v in values if v is not None]
    if not known:
        return None, False
    return sum(known), len(known) != len(values)


def reconcile(
    category: str,
    observations: list[RequestObservation],
    provider_reported: float | None,
) -> Reconciled:
    app, partial = app_sum(observations, category)
    if app is None and provider_reported is None:
        return Reconciled(category, Status.UNKNOWN, None, None, None, None, False)
    if provider_reported is None:
        return Reconciled(category, Status.APP_ONLY, app, None, float(app), None, partial)
    if app is None:
        return Reconciled(
            category, Status.PROVIDER_ONLY, None, provider_reported, provider_reported, None, False
        )
    if app > provider_reported:
        return Reconciled(
            category, Status.APP_EXCEEDS_PROVIDER, app, provider_reported, float(app), None, partial
        )
    # Provider is the superset view; the gap is traffic the app did not route.
    # With partial request data the gap is an upper bound, so it is withheld.
    gap = None if partial else provider_reported - app
    return Reconciled(
        category, Status.RECONCILED, app, provider_reported, provider_reported, gap, partial
    )
