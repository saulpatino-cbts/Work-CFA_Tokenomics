"""Usage observation value objects (docs/token-accounting.md).

Token categories are nullable: ``None`` means unknown and is never treated as zero.
Categories keep the provider's own meaning; nothing here sums across categories.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

CATEGORIES = ("input", "output", "cache_read", "cache_write", "reasoning", "total")
# How the usage was bought. "unknown" is the honest default: never guessed from a model name.
SKUS = ("api_on_demand", "api_provisioned", "subscription", "unknown")
# Where the observation came from. Sources are kept apart; the same traffic can appear in more
# than one and is never added across them.
SOURCE_TYPES = ("cloud_telemetry", "vendor_admin_api", "app_routed")


class Quality(StrEnum):
    REPORTED = "reported"
    ESTIMATED = "estimated"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


def _check_dims(sku: str, source_type: str) -> None:
    if sku not in SKUS:
        raise ValueError(f"unknown sku {sku!r}")
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"unknown source_type {source_type!r}")


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
    sku: str = "unknown"
    source_type: str = "app_routed"

    def __post_init__(self) -> None:
        _check_dims(self.sku, self.source_type)

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
    sku: str = "unknown"
    source_type: str = "cloud_telemetry"

    def __post_init__(self) -> None:
        _check_dims(self.sku, self.source_type)
        if self.category not in CATEGORIES:
            raise ValueError(f"unknown category {self.category!r}")
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
