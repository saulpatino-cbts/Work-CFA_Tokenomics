"""Anthropic usage and cost connector (aggregate mode), reading the Admin API's analytics endpoints.

GET /v1/organizations/analytics/usage and /cost (beta, header ``anthropic-beta: analytics-usage-cost-2026-08-24``).
Response shapes are those in docs/economics/09-vendor-api-research.md and were read from the vendor's
documentation, not from a live call: **nothing here has been run against the real API.**

What it does, and what it does not:
- Aggregate mode only. The request never groups by person (no ``actor``), and no email, name or user id is
  read. ``per_user`` is refused until its storage exists (ADR 0012).
- Read-only. The Admin API key is a credential reference (``env:`` or ``file:``) resolved when a request is
  made. The host is fixed, so the key cannot be sent anywhere else. The key never appears in an error.
- Usage tokens go to the usage ledger (``usage_aggregate_observations``), summed over service tier, speed and
  context window because the ledger has no such dimensions. Cost goes in as FOCUS-shaped rows through the
  FOCUS importer, so it gets lineage, revision handling and finality like any other cost source.
- Amounts are decimal strings in cents. ``amount`` (after discounts, before credits) fills BilledCost,
  EffectiveCost and ContractedCost, and ``list_amount`` fills ListCost. Credits are not visible in this API,
  so BilledCost is NOT the invoiced amount: ``x_BilledCostIsPreCredit`` says so, and the invoice stays
  authoritative. Priority Tier commitment fees are not in this data.
- A bucket newer than the response's ``data_refreshed_at`` is partial or missing, so it is not stored yet.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
import uuid
from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..focus import tables as T
from ..focus.importer import import_focus_file
from ..privacy import Mode, parse_mode
from ..usage import ledger
from ..usage.models import AggregateObservation, Quality
from . import credentials
from .costexport import ConfigError, Outcome, Step

BASE_URL = "https://api.anthropic.com"  # fixed: the credential can only go here
API_VERSION = "2026-10-21"
BETA = "analytics-usage-cost-2026-08-24"
MIN_START = datetime(2026, 1, 1, tzinfo=UTC)  # the API refuses earlier dates
MAX_SPAN = timedelta(days=31)
PAGE_LIMIT = 1000
MAX_PAGES = 200
MAX_ATTEMPTS = 5
MAX_RESTARTS = 2
FINAL_AFTER_MONTH_END = timedelta(days=7)  # values can change until about 7 days after month end
# The five dimensions that aggregate mode may group by. Never ``actor``.
USAGE_GROUPS = ("model", "workspace_id", "service_tier", "speed", "context_window")
TOKEN_TYPES = (
    "uncached_input_tokens",
    "cache_creation.ephemeral_5m_input_tokens",
    "cache_creation.ephemeral_1h_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)
_ALLOWED = {"credential_ref", "mode", "lookback_days", "billing_account_id"}
_ACCOUNT = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_MONEY = re.compile(r"^-?\d+(\.\d+)?$")
NORMALIZATION = "anthropic-analytics-1"
MANIFEST = {
    "source": "Anthropic Admin API usage and cost analytics (beta)",
    "auth": "an Admin API key (or an Analytics key with read:analytics for Claude Enterprise), as a credential reference",
    "delay": "typically within 4 hours, up to 24; values revised until about 7 days after month end",
    "limits": "60 requests per minute per organization; at most 31 days per request; 1,000 rows per page",
    "privacy": "aggregate mode never groups by person; per-user mode is not built",
}


class SourceError(Exception):
    """A failure talking to the source. The message never contains the credential or a response body."""


class _CursorExpired(Exception):
    pass


@dataclass(frozen=True)
class AnthropicConfig:
    credential_ref: str
    mode: Mode = Mode.AGGREGATE
    lookback_days: int = 35
    billing_account_id: str = "anthropic"


def parse_scope(scope: dict, credential_ref: str | None = None) -> AnthropicConfig:
    scope = dict(scope)
    unknown = sorted(set(scope) - _ALLOWED)
    if unknown:
        raise ConfigError(
            f"unknown setting(s): {', '.join(unknown)}. A key is never a setting; use credential_ref"
        )
    ref = credential_ref or scope.get("credential_ref")
    if not ref:
        raise ConfigError("credential_ref is required, for example env:ANTHROPIC_ADMIN_KEY")
    try:
        credentials.check_ref(ref)
        mode = parse_mode(scope.get("mode"))
    except ValueError as exc:
        raise ConfigError(str(exc)) from None
    if mode is Mode.PER_USER:
        raise ConfigError(
            "per_user mode is not built yet: its pseudonymized storage does not exist (ADR 0012); use aggregate"
        )
    days = scope.get("lookback_days", 35)
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 365:
        raise ConfigError("lookback_days must be a whole number from 1 to 365")
    acct = scope.get("billing_account_id", "anthropic")
    if not isinstance(acct, str) or not _ACCOUNT.match(acct):
        raise ConfigError("billing_account_id must be 1 to 128 letters, digits or . _ : -")
    return AnthropicConfig(ref, mode, days, acct)


def create_connector(db: Session, tenant_id: uuid.UUID, name: str, scope: dict) -> uuid.UUID:
    cfg = parse_scope(scope)
    stored = {
        "mode": cfg.mode.value,
        "lookback_days": cfg.lookback_days,
        "billing_account_id": cfg.billing_account_id,
    }
    cid = uuid.uuid4()
    db.execute(
        insert(T.connectors).values(
            id=cid,
            tenant_id=tenant_id,
            provider_key="anthropic",
            kind="api",
            name=name,
            credential_ref=cfg.credential_ref,
            scope=stored,
            enabled=True,
        )  # fmt: skip
    )
    db.commit()
    return cid


# ---- the HTTP client ------------------------------------------------------------------------------------


class Client:
    """Read-only access to the analytics endpoints. Paced under the documented rate limit, with bounded
    retries. The key is resolved on first use and held only in memory."""

    def __init__(
        self,
        credential_ref: str,
        http: httpx.Client | None = None,
        sleep=time.sleep,
        min_interval: float = 1.1,
    ):
        self._ref = credential_ref
        self._http = http or httpx.Client(base_url=BASE_URL, timeout=30.0)
        self._sleep = sleep
        self._min_interval = min_interval
        self._last = 0.0

    def __repr__(self) -> str:
        return "Client(<credential withheld>)"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": credentials.resolve(self._ref), "anthropic-version": API_VERSION, "anthropic-beta": BETA,
            "user-agent": "cfa-tokenomics/0 (read-only cost connector)",
        }  # fmt: skip

    def _get(self, path: str, params: list[tuple[str, str]]) -> dict:
        headers = self._headers()
        for attempt in range(MAX_ATTEMPTS):
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()
            try:
                res = self._http.get(path, params=params, headers=headers)
            except httpx.TransportError as exc:
                if attempt == MAX_ATTEMPTS - 1:
                    raise SourceError(
                        f"the Anthropic API could not be reached ({type(exc).__name__})"
                    ) from None
                self._sleep(min(2**attempt, 30))
                continue
            if res.status_code == 200:
                try:
                    body = res.json()
                except ValueError:
                    raise SourceError(
                        "the Anthropic API returned something that is not JSON"
                    ) from None
                if not isinstance(body, dict):
                    raise SourceError("the Anthropic API returned an unexpected response shape")
                return body
            if res.status_code == 410:
                raise _CursorExpired
            if res.status_code in (429, 500, 502, 503, 504):
                if attempt == MAX_ATTEMPTS - 1:
                    raise SourceError(
                        f"the Anthropic API kept refusing the request (HTTP {res.status_code})"
                    )
                retry = res.headers.get("retry-after", "")
                self._sleep(
                    min(float(retry), 60)
                    if retry.replace(".", "", 1).isdigit()
                    else min(2**attempt, 30)
                )
                continue
            if res.status_code in (401, 403):
                raise SourceError(
                    f"the Anthropic API rejected the credential or it lacks Admin API access (HTTP {res.status_code})"
                )
            if res.status_code == 400:
                raise SourceError("the Anthropic API rejected the request parameters (HTTP 400)")
            raise SourceError(f"the Anthropic API returned HTTP {res.status_code}")
        raise SourceError("the Anthropic API request did not complete")  # pragma: no cover

    def get_all(self, path: str, params: list[tuple[str, str]]) -> tuple[list[dict], str | None]:
        """Every page of one query. A cursor that expires mid-way (the data was refreshed) restarts the query."""
        for _ in range(MAX_RESTARTS + 1):
            try:
                return self._pages(path, params)
            except _CursorExpired:
                continue
        raise SourceError(
            "the Anthropic data kept being refreshed while it was read; try again later"
        )

    def _pages(self, path: str, params: list[tuple[str, str]]) -> tuple[list[dict], str | None]:
        rows: list[dict] = []
        refreshed: str | None = None
        page: str | None = None
        for n in range(MAX_PAGES):
            body = self._get(path, params + ([("page", page)] if page else []))
            data = body.get("data")
            if not isinstance(data, list) or not isinstance(body.get("has_more"), bool):
                raise SourceError("the Anthropic API returned an unexpected response shape")
            rows += data
            if n == 0:
                refreshed = body.get("data_refreshed_at")
                if refreshed is not None and not isinstance(refreshed, str):
                    raise SourceError("the Anthropic API returned an unexpected data_refreshed_at")
            if not body["has_more"]:
                return rows, refreshed
            page = body.get("next_page")
            if not isinstance(page, str) or not page:
                raise SourceError("the Anthropic API said there was more data but gave no cursor")
        raise SourceError("the Anthropic data spans more pages than this connector will read")


def build_client(cfg: AnthropicConfig) -> Client:
    return Client(cfg.credential_ref)


# ---- windows and parsing ----------------------------------------------------------------------------------


def windows(cfg: AnthropicConfig, now: datetime | None = None) -> list[tuple[datetime, datetime]]:
    """Day-aligned windows of at most 31 days, up to the start of today (UTC): today is still being filled."""
    now = now or datetime.now(UTC)
    end = datetime(now.year, now.month, now.day, tzinfo=UTC)
    start = max(MIN_START, end - timedelta(days=cfg.lookback_days))
    out = []
    while start < end:
        stop = min(start + MAX_SPAN, end)
        out.append((start, stop))
        start = stop
    return out


def _ts(value: Any, what: str) -> datetime:
    if not isinstance(value, str):
        raise SourceError(f"a {what} timestamp was not text")
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SourceError(f"a {what} timestamp was not valid") from None
    if t.tzinfo is None:
        raise SourceError(f"a {what} timestamp had no time zone")
    return t.astimezone(UTC)


def _count(value: Any, what: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or value < 0
        or value != int(value)
    ):
        raise SourceError(f"a {what} count was not a non-negative whole number")
    return int(value)


@dataclass(frozen=True)
class Dims:
    start: datetime
    end: datetime
    model: str | None
    workspace: str | None
    tier: str | None
    speed: str | None
    context: str | None

    @property
    def key(self) -> tuple:
        return (self.start, self.model, self.workspace, self.tier, self.speed, self.context)


def _dims(row: dict) -> Dims:
    g = row.get("group")
    if not isinstance(g, dict):
        raise SourceError("a row had no group object")
    for banned in ("actor", "actor_type", "claude_tag_user_id", "user_profile_id"):
        if (
            g.get(banned) is not None
        ):  # aggregate mode asked for none of these; refuse and drop if sent anyway
            raise SourceError(
                "the source returned person-level data in aggregate mode; nothing was stored"
            )
    return Dims(_ts(row.get("starting_at"), "starting_at"), _ts(row.get("ending_at"), "ending_at"),
                g.get("model"), g.get("workspace_id"), g.get("service_tier"), g.get("speed"), g.get("context_window"))  # fmt: skip


def parse_usage(rows: list[dict]) -> dict[tuple, tuple[Dims, dict[str, int]]]:
    """Dimension key to the five token counts. Only the counts and dimensions are read, nothing else."""
    out: dict[tuple, tuple[Dims, dict[str, int]]] = {}
    for row in rows:
        d = _dims(row)
        u = row.get("usage")
        if not isinstance(u, dict):
            raise SourceError("a usage row had no usage object")
        cc = u.get("cache_creation") or {}
        counts = {
            "uncached_input_tokens": _count(
                u.get("uncached_input_tokens", 0), "uncached_input_tokens"
            ),
            "cache_creation.ephemeral_5m_input_tokens": _count(
                cc.get("ephemeral_5m_input_tokens", 0), "cache creation 5m"
            ),
            "cache_creation.ephemeral_1h_input_tokens": _count(
                cc.get("ephemeral_1h_input_tokens", 0), "cache creation 1h"
            ),
            "cache_read_input_tokens": _count(
                u.get("cache_read_input_tokens", 0), "cache_read_input_tokens"
            ),
            "output_tokens": _count(u.get("output_tokens", 0), "output_tokens"),
        }
        if d.key in out:
            raise SourceError("the source returned the same usage group twice")
        out[d.key] = (d, counts)
    return out


def usage_observations(
    usage: dict[tuple, tuple[Dims, dict[str, int]]],
) -> list[AggregateObservation]:
    """Ledger observations, summed over tier, speed and context window (the ledger has no such dimensions).
    ``input`` is Anthropic's uncached input; cache reads and writes keep their own categories."""
    sums: dict[tuple, dict[str, int]] = {}
    for d, c in usage.values():
        s = sums.setdefault((d.start, d.end, d.workspace or "default", d.model or "unknown"), dict.fromkeys(
            ("input", "output", "cache_read", "cache_write", "total"), 0))  # fmt: skip
        s["input"] += c["uncached_input_tokens"]
        s["output"] += c["output_tokens"]
        s["cache_read"] += c["cache_read_input_tokens"]
        s["cache_write"] += (
            c["cache_creation.ephemeral_5m_input_tokens"]
            + c["cache_creation.ephemeral_1h_input_tokens"]
        )
        s["total"] += sum(c.values())
    obs = []
    for (start, end, account, model), s in sorted(sums.items()):
        for category, value in s.items():
            obs.append(AggregateObservation(
                "anthropic", account, model, category, start, end, "Sum", float(value), Quality.REPORTED,
                NORMALIZATION, "unknown", "vendor_admin_api",
            ))  # fmt: skip
    return obs


_DIRECTION = {
    "uncached_input_tokens": ("Input", "Uncached"),
    "cache_creation.ephemeral_5m_input_tokens": ("Input", "Write"),
    "cache_creation.ephemeral_1h_input_tokens": ("Input", "Write"),
    "cache_read_input_tokens": ("Input", "Read"),
    "output_tokens": ("Output", None),
}
FOCUS_COLUMNS = [
    "BilledCost", "EffectiveCost", "ListCost", "ContractedCost", "ChargeCategory", "ChargeDescription",
    "ChargePeriodStart", "ChargePeriodEnd", "BillingPeriodStart", "BillingPeriodEnd", "BillingCurrency",
    "BillingAccountId", "SubAccountId", "ServiceName", "ServiceCategory", "ServiceProviderName",
    "HostProviderName", "InvoiceIssuerName", "ConsumedQuantity", "ConsumedUnit", "SkuId", "SkuPriceId",
    "SkuMeter", "SkuPriceDetails", "x_ServiceTier", "x_Speed", "x_ContextWindow", "x_CostType",
    "x_TokenType", "x_BilledCostIsPreCredit",
]  # fmt: skip


def _usd(cents: Any, what: str) -> Decimal:
    if not isinstance(cents, str) or not _MONEY.match(cents):
        raise SourceError(f"a {what} was not a decimal string")
    with localcontext() as ctx:
        ctx.prec = 60
        return Decimal(cents) / 100


def cost_csv(
    rows: list[dict], usage: dict[tuple, tuple[Dims, dict[str, int]]], cfg: AnthropicConfig
) -> tuple[bytes, int]:
    """FOCUS-shaped CSV for the cost rows. Token counts are joined from the usage rows of the same group,
    so cost per million tokens works; a cost row with no matching usage simply has no quantity."""
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=FOCUS_COLUMNS, lineterminator="\n")
    w.writeheader()
    n = 0
    for row in rows:
        d = _dims(row)
        c = row.get("cost")
        if not isinstance(c, dict):
            raise SourceError("a cost row had no cost object")
        if c.get("currency") != "USD":
            raise SourceError(
                "a cost row was not in USD; this connector will not guess a conversion"
            )
        amount, listed = _usd(c.get("amount"), "amount"), _usd(c.get("list_amount"), "list_amount")
        g = row["group"]
        ctype, ttype = g.get("cost_type"), g.get("token_type")
        qty = None
        if ctype == "tokens" and ttype in _DIRECTION:
            hit = usage.get(d.key)
            qty = hit[1][ttype] if hit else None
        month_first = d.start.replace(day=1)
        month_end = month_first.replace(day=monthrange(d.start.year, d.start.month)[1]) + timedelta(
            days=1
        )
        sku = f"{d.model or 'unknown'}:{ttype or ctype or 'cost'}"
        price_id = f"anthropic:{sku}:{d.tier or '-'}:{d.context or '-'}"
        props = None
        if ctype == "tokens" and ttype in _DIRECTION and d.model:
            direction, action = _DIRECTION[ttype]
            p = {"ModelDeveloper": "Anthropic", "ModelId": d.model, "TokenDirection": direction}
            if action:
                p["TokenCacheAction"] = action
            props = json.dumps(p, sort_keys=True, separators=(",", ":"))
        w.writerow({
            "BilledCost": f"{amount:f}", "EffectiveCost": f"{amount:f}", "ListCost": f"{listed:f}", "ContractedCost": f"{amount:f}",
            "ChargeCategory": "Usage", "ChargeDescription": f"{d.model or 'Claude API'} {ttype or ctype or ''}".strip(),
            "ChargePeriodStart": d.start.strftime("%Y-%m-%dT%H:%M:%SZ"), "ChargePeriodEnd": d.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "BillingPeriodStart": month_first.strftime("%Y-%m-%dT%H:%M:%SZ"), "BillingPeriodEnd": month_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "BillingCurrency": "USD", "BillingAccountId": cfg.billing_account_id, "SubAccountId": d.workspace or "default",
            "ServiceName": "Claude API", "ServiceCategory": "AI and Machine Learning", "ServiceProviderName": "Anthropic",
            "HostProviderName": "Anthropic", "InvoiceIssuerName": "Anthropic",
            "ConsumedQuantity": "" if qty is None else str(qty), "ConsumedUnit": "" if qty is None else "Tokens",
            "SkuId": sku, "SkuPriceId": price_id if props else "", "SkuMeter": ttype or ctype or "", "SkuPriceDetails": props or "",
            "x_ServiceTier": d.tier or "", "x_Speed": d.speed or "", "x_ContextWindow": d.context or "", "x_CostType": ctype or "",
            "x_TokenType": ttype or "", "x_BilledCostIsPreCredit": "true",
        })  # fmt: skip
        n += 1
    return out.getvalue().encode(), n


# ---- check and pull ---------------------------------------------------------------------------------------


def _params(start: datetime, end: datetime, cost: bool) -> list[tuple[str, str]]:
    p = [("starting_at", start.strftime("%Y-%m-%dT%H:%M:%SZ")), ("ending_at", end.strftime("%Y-%m-%dT%H:%M:%SZ")),
         ("time_bucket_width", "1d"), ("limit", str(PAGE_LIMIT))]  # fmt: skip
    p += [("group_by[]", g) for g in USAGE_GROUPS]
    if cost:
        p += [("group_by[]", "cost_type"), ("group_by[]", "token_type")]
    return p


def check(cfg: AnthropicConfig, client: Client, now: datetime | None = None) -> list[Step]:
    steps = [
        Step(
            "configuration",
            True,
            f"aggregate mode, {cfg.lookback_days} days back, billing account {cfg.billing_account_id}",
        )
    ]
    try:
        credentials.resolve(cfg.credential_ref)
    except credentials.CredentialError as exc:
        steps.append(Step("credential", False, str(exc)))
        return steps
    steps.append(
        Step(
            "credential",
            True,
            f"{cfg.credential_ref.split(':')[0]} reference resolves (value not shown)",
        )
    )
    now = now or datetime.now(UTC)
    end = datetime(now.year, now.month, now.day, tzinfo=UTC)
    try:
        rows, refreshed = client.get_all(
            "/v1/organizations/analytics/usage",
            _params(max(MIN_START, end - timedelta(days=2)), end, False),
        )
    except SourceError as exc:
        steps.append(Step("access", False, str(exc)))
        return steps
    steps.append(Step("access", True, "the analytics endpoint answered"))
    if refreshed is None:
        steps.append(Step("data", False, "the source has no data yet (data_refreshed_at is empty)"))
    elif not rows:
        steps.append(
            Step("data", False, f"no usage in the last two days (data refreshed {refreshed})")
        )
    else:
        steps.append(Step("data", True, f"{len(rows)} usage group(s); data refreshed {refreshed}"))
    return steps


def _final(last_end: datetime, refreshed: datetime) -> bool:
    month_end = (last_end - timedelta(days=1)).replace(day=1)
    month_end = month_end.replace(day=monthrange(month_end.year, month_end.month)[1]) + timedelta(
        days=1
    )
    return month_end + FINAL_AFTER_MONTH_END <= refreshed


def pull(
    db: Session,
    tenant_id: uuid.UUID,
    connector_id: uuid.UUID,
    cfg: AnthropicConfig,
    client: Client,
    now: datetime | None = None,
) -> list[Outcome]:
    """Read each window's usage and cost, store complete days only, and report what happened per window."""
    out: list[Outcome] = []
    for start, end in windows(cfg, now):
        o = Outcome(f"{start:%Y-%m-%d}..{end:%Y-%m-%d}", "", "")
        out.append(o)
        try:
            urows, refreshed_s = client.get_all(
                "/v1/organizations/analytics/usage", _params(start, end, False)
            )
            crows, refreshed_c = client.get_all(
                "/v1/organizations/analytics/cost", _params(start, end, True)
            )
            if refreshed_s is None or refreshed_c is None:
                o.status, o.detail = (
                    "no_data",
                    "the source has no data yet (data_refreshed_at is empty)",
                )
                continue
            refreshed = min(
                _ts(refreshed_s, "data_refreshed_at"), _ts(refreshed_c, "data_refreshed_at")
            )
            usage = {k: v for k, v in parse_usage(urows).items() if v[0].end <= refreshed}
            keep = [r for r in crows if _ts(r.get("ending_at"), "ending_at") <= refreshed]
            deferred = len(crows) - len(keep)
            counts = {"inserted": 0, "revised": 0, "unchanged": 0}
            for ob in usage_observations(usage):
                counts[ledger.upsert_aggregate(db, ob)] += 1
            if not keep:
                o.status = "no_data" if not crows else "deferred"
                o.detail = f"usage {counts}; no complete cost days yet"
                continue
            content, n = cost_csv(keep, usage, cfg)
            last_end = max(_ts(r["ending_at"], "ending_at") for r in keep)
            name = f"anthropic:{cfg.billing_account_id}:{start:%Y%m%d}-{end:%Y%m%d}@{hashlib.sha256(content).hexdigest()[:12]}"
            res = import_focus_file(
                db, tenant_id, connector_id, name, content, declared_version="unknown",
                finality="final" if _final(last_end, refreshed) else "provisional", now=now,
            )  # fmt: skip
            o.rows, o.superseded = res.rows_imported, res.superseded
            note = f"usage {counts}" + (
                f"; {deferred} cost group(s) newer than data_refreshed_at left for later"
                if deferred
                else ""
            )
            if res.status == "duplicate":
                o.status, o.detail = "already_imported", note
            elif res.status in ("succeeded", "partial"):
                o.status = "imported" if res.status == "succeeded" else "partial"
                o.detail = f"{n} cost row(s); {note}"
            else:
                o.status, o.detail = "failed", res.error or "import failed"
        except (SourceError, credentials.CredentialError) as exc:
            o.status, o.detail = "failed", str(exc)
            break  # the same credential or endpoint would fail the remaining windows too
    return out
