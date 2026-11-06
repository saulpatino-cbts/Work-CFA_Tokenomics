"""Usage observation value objects (docs/token-accounting.md).

Token categories are nullable: ``None`` means unknown and is never treated as zero.
Categories keep the provider's own meaning; nothing here sums across categories.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

CATEGORIES = ("input", "output", "cache_read", "cache_write", "reasoning", "total")


class Quality(StrEnum):
    REPORTED = "reported"
    ESTIMATED = "estimated"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RequestObservation:
    provider: str
    account: str  # customer-controlled scope id (account/subscription/project)
    request_id: str
    attempt: int
    model_id: str
    occurred_at: datetime
    input: int | None = None
    output: int | None = None
    cache_read: int | None = None
    cache_write: int | None = None
    reasoning: int | None = None
    total: int | None = None  # provider-reported total, kept as supplied
    quality: Quality = Quality.REPORTED
    normalization_version: str = "1"
    metadata: dict = field(default_factory=dict)  # usage-only; never content or credentials

    @property
    def source_key(self) -> str:
        return f"{self.provider}|{self.account}|{self.request_id}|{self.attempt}"


@dataclass(frozen=True)
class AggregateObservation:
    provider: str
    account: str
    model_id: str
    category: str
    window_start: datetime
    window_end: datetime
    statistic: str
    value: float
    quality: Quality = Quality.REPORTED
    normalization_version: str = "1"

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"unknown category {self.category!r}")
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
