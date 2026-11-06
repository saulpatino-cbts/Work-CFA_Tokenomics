"""Provider adapter contract (docs/providers.md). Adapters never receive or return secrets."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..usage.models import AggregateObservation


@dataclass(frozen=True)
class CollectionWindow:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class CollectionResult:
    observations: list[AggregateObservation]
    complete: bool  # False if the provider reported partial data; cursor must not advance
    next_cursor: str | None


class AggregateCollector(Protocol):
    provider: str

    def collect(self, window: CollectionWindow, cursor: str | None) -> CollectionResult: ...
