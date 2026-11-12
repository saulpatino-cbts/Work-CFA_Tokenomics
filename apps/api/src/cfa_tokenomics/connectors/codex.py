"""OpenAI Codex and ChatGPT Enterprise connector (aggregate mode), reading the unified Daily Usage API.

GET https://api.chatgpt.com/v1/analytics/workspaces/{workspace_id}/usage with ``group=workspace``. The
shape and semantics are those in the vendor's OpenAPI file (docs/economics/09-vendor-api-research.md);
**nothing here has been run against the real API.**

What it does, and what it does not:
- Aggregate mode only. ``group=workspace`` returns one workspace-wide row per UTC day, so no user id or email
  is requested. A row that carries one anyway is refused. ``per_user`` is refused until its storage exists.
- Read-only, with the Admin key given as a credential reference (``env:`` or ``file:``). The host is fixed.
- Credits and native USD are reported separately by the source and are **never converted** here.
  - Native USD-priced usage (``cost_usd``) is stored as cost with basis ``observed``: the vendor reports it,
    though it is not a final invoice amount.
  - Credit-priced usage is stored as cost only where the source gives ``estimated_cost_usd`` (an estimate
    at the workspace's *current credit overage rate*), with basis ``estimated`` and the credits kept exactly
    in ``x_Credits``. An estimate is never labelled observed. Credits with no estimate are counted, not
    priced.
  - The two streams use different SubAccountIds so that one revising never supersedes the other.
- Text tokens exist only for API-priced usage. They go to the usage ledger where present; a missing field is
  unknown, never zero, and a reported zero stays zero.
- Amounts arrive as JSON numbers, so the client parses them straight into Decimal, never through a float.
- Activity counts (chats, messages) are not stored: the ledger holds token categories only.
- The API says recent rows may be corrected and gives no window, so cost stays provisional for
  ``final_after_days`` (default 30, an assumption). Today is never read: it is still being filled.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import time
import uuid
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
from .paged import PagedClient, SourceError, day_windows

BASE_URL = "https://api.chatgpt.com/v1"  # fixed: the credential can only go here
PATH = "/analytics/workspaces/{workspace_id}/usage"
PAGE_LIMIT = 1000
SPAN = timedelta(days=31)
NORMALIZATION = "openai-daily-usage-1"
PROVIDER = "openai_codex"
_ALLOWED = {
    "credential_ref",
    "workspace_id",
    "mode",
    "lookback_days",
    "final_after_days",
    "billing_account_id",
}
_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
TOKEN_FIELDS = (
    "uncached_text_input_tokens",
    "cached_text_input_tokens",
    "text_output_tokens",
    "text_total_tokens",
)
MANIFEST = {
    "source": "OpenAI unified Daily Usage API (ChatGPT Enterprise workspaces: ChatGPT, Codex and Work)",
    "auth": "an Admin key with the enterprise.analytics.usage read scope, as a credential reference",
    "delay": "eventually consistent: recent daily rows may be corrected; no correction window is stated",
    "limits": "100 requests per minute per workspace per route; up to 30,000 rows per page",
    "privacy": "aggregate mode uses group=workspace; per-user mode is not built",
}


@dataclass(frozen=True)
class CodexConfig:
    credential_ref: str
    workspace_id: str
    mode: Mode = Mode.AGGREGATE
    lookback_days: int = 35
    final_after_days: int = 30
    billing_account_id: str = "openai-chatgpt-enterprise"


def parse_scope(scope: dict, credential_ref: str | None = None) -> CodexConfig:
    scope = dict(scope)
    unknown = sorted(set(scope) - _ALLOWED)
    if unknown:
        raise ConfigError(
            f"unknown setting(s): {', '.join(unknown)}. A key is never a setting; use credential_ref"
        )
    ref = credential_ref or scope.get("credential_ref")
    if not ref:
        raise ConfigError("credential_ref is required, for example env:OPENAI_ADMIN_KEY")
    try:
        credentials.check_ref(ref)
        mode = parse_mode(scope.get("mode"))
    except ValueError as exc:
        raise ConfigError(str(exc)) from None
    if mode is Mode.PER_USER:
        raise ConfigError(
            "per_user mode is not built yet: its pseudonymized storage does not exist (ADR 0012); use aggregate"
        )
    ws = scope.get("workspace_id")
    if not isinstance(ws, str) or not _ID.match(ws):
        raise ConfigError(
            "workspace_id is required: the ChatGPT Enterprise workspace id (letters, digits, . _ : -)"
        )
    days = scope.get("lookback_days", 35)
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 365:
        raise ConfigError("lookback_days must be a whole number from 1 to 365")
    fin = scope.get("final_after_days", 30)
    if not isinstance(fin, int) or isinstance(fin, bool) or not 7 <= fin <= 90:
        raise ConfigError("final_after_days must be a whole number from 7 to 90")
    acct = scope.get("billing_account_id", "openai-chatgpt-enterprise")
    if not isinstance(acct, str) or not _ID.match(acct):
        raise ConfigError("billing_account_id must be 1 to 128 letters, digits or . _ : -")
    return CodexConfig(ref, ws, mode, days, fin, acct)


def create_connector(db: Session, tenant_id: uuid.UUID, name: str, scope: dict) -> uuid.UUID:
    cfg = parse_scope(scope)
    stored = {"workspace_id": cfg.workspace_id, "mode": cfg.mode.value, "lookback_days": cfg.lookback_days,
              "final_after_days": cfg.final_after_days, "billing_account_id": cfg.billing_account_id}  # fmt: skip
    cid = uuid.uuid4()
    db.execute(
        insert(T.connectors).values(
            id=cid,
            tenant_id=tenant_id,
            provider_key=PROVIDER,
            kind="api",
            name=name,
            credential_ref=cfg.credential_ref,
            scope=stored,
            enabled=True,
        )  # fmt: skip
    )
    db.commit()
    return cid


def _headers(key: str) -> dict[str, str]:
    return {
        "authorization": f"Bearer {key}",
        "user-agent": "cfa-tokenomics/0 (read-only cost connector)",
    }


class Client(PagedClient):
    """Read-only access to the Daily Usage endpoint, paced under 100 requests per minute (about 0.7 s apart).
    Numbers are parsed as Decimal straight from the response text."""

    def __init__(
        self,
        credential_ref: str,
        http: httpx.Client | None = None,
        sleep=time.sleep,
        min_interval: float = 0.7,
    ):
        super().__init__(
            "OpenAI",
            BASE_URL,
            credential_ref,
            _headers,
            http,
            sleep,
            min_interval,
            decimal_numbers=True,
        )


def build_client(cfg: CodexConfig) -> Client:
    return Client(cfg.credential_ref)


def windows(cfg: CodexConfig, now: datetime | None = None) -> list[tuple[datetime, datetime]]:
    return day_windows(cfg.lookback_days, now, None, SPAN)


def _params(start: datetime, end: datetime) -> list[tuple[str, str]]:
    return [("start_time", str(int(start.timestamp()))), ("end_time", str(int(end.timestamp()))),
            ("limit", str(PAGE_LIMIT)), ("group", "workspace")]  # fmt: skip


# ---- parsing ----------------------------------------------------------------------------------------------


def _dec(value: Any, what: str) -> Decimal | None:
    """None stays unknown. A reported zero stays zero."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | Decimal) or value < 0:
        raise SourceError(f"a {what} amount was not a non-negative number")
    return Decimal(value)


def _tokens(obj: dict, what: str) -> dict[str, int]:
    out = {}
    for f in TOKEN_FIELDS:
        if f in obj and obj[f] is not None:
            v = obj[f]
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise SourceError(f"a {what} {f} count was not a non-negative whole number")
            out[f] = v
    return out


@dataclass(frozen=True)
class Slice:
    """One day's usage for one model and speed, or the remainder not attributed to any model."""

    model: str | None
    speed: str | None
    credits: Decimal | None
    usd: Decimal | None
    estimated: Decimal | None
    tokens: dict[str, int]


@dataclass(frozen=True)
class Day:
    start: datetime
    end: datetime
    slices: tuple[Slice, ...]


def _slice(o: dict, what: str, model: str | None = None, speed: str | None = None) -> Slice:
    return Slice(model, speed, _dec(o.get("credits"), what), _dec(o.get("cost_usd"), what),
                 _dec(o.get("estimated_cost_usd"), what), _tokens(o, what))  # fmt: skip


def parse_days(rows: list[dict]) -> list[Day]:
    days: list[Day] = []
    seen: set[int] = set()
    for row in rows:
        if row.get("user_id") is not None or row.get("actor") is not None:
            raise SourceError(
                "the source returned person-level data in aggregate mode; nothing was stored"
            )
        st, en = row.get("start_time"), row.get("end_time")
        if (
            isinstance(st, bool)
            or isinstance(en, bool)
            or not isinstance(st, int)
            or not isinstance(en, int)
        ):
            raise SourceError("a row's start_time or end_time was not a whole number")
        if st % 86400 or en != st + 86400:
            raise SourceError("a row was not exactly one UTC day")
        if st in seen:
            raise SourceError("the source returned the same day twice")
        seen.add(st)
        totals = row.get("totals")
        if not isinstance(totals, dict):
            raise SourceError("a row had no totals object")
        whole = _slice(totals, "total")
        models = row.get("models") or []
        if not isinstance(models, list):
            raise SourceError("a row's models was not a list")
        parts = []
        for m in models:
            if not isinstance(m, dict) or not isinstance(m.get("model"), str):
                raise SourceError("a model entry had no model name")
            parts.append(_slice(m, "model", m["model"], m.get("speed")))
        # Whatever the totals hold that the model rows do not is real usage with no model attribution.
        rest = Slice(
            None, None,
            _remainder(whole.credits, [p.credits for p in parts]),
            _remainder(whole.usd, [p.usd for p in parts]),
            _remainder(whole.estimated, [p.estimated for p in parts]),
            {f: v - sum(p.tokens.get(f, 0) for p in parts) for f, v in whole.tokens.items() if v - sum(p.tokens.get(f, 0) for p in parts) > 0},
        )  # fmt: skip
        keep = list(parts)
        if (
            rest.credits
            or rest.usd
            or rest.estimated
            or rest.tokens
            or (not parts and (whole.credits is not None or whole.usd is not None))
        ):
            keep.append(rest)
        days.append(
            Day(datetime.fromtimestamp(st, UTC), datetime.fromtimestamp(en, UTC), tuple(keep))
        )
    return days


def _remainder(total: Decimal | None, parts: list[Decimal | None]) -> Decimal | None:
    if total is None:
        return None
    left = total - sum((p for p in parts if p is not None), Decimal(0))
    return left if left > 0 else None


def usage_observations(days: list[Day], workspace_id: str) -> list[AggregateObservation]:
    """Text tokens per day and model, summed over speed. Only API-priced usage has tokens, and only the fields
    the source gave: a missing field is unknown and produces no observation."""
    sums: dict[tuple, dict[str, int]] = {}
    for d in days:
        for s in d.slices:
            if not s.tokens:
                continue
            into = sums.setdefault((d.start, d.end, s.model or "unknown"), {})
            for f, v in s.tokens.items():
                into[f] = into.get(f, 0) + v
    mapping = {"uncached_text_input_tokens": "input", "cached_text_input_tokens": "cache_read",
               "text_output_tokens": "output", "text_total_tokens": "total"}  # fmt: skip
    obs = []
    for (start, end, model), fields in sorted(sums.items()):
        for f, v in fields.items():
            obs.append(AggregateObservation(PROVIDER, workspace_id, model, mapping[f], start, end, "Sum", float(v), Quality.REPORTED, NORMALIZATION, "unknown", "vendor_admin_api"))  # fmt: skip
    return obs


# ---- cost ---------------------------------------------------------------------------------------------------

COLUMNS = [
    "BilledCost", "EffectiveCost", "ListCost", "ContractedCost", "ChargeCategory", "ChargeDescription",
    "ChargePeriodStart", "ChargePeriodEnd", "BillingPeriodStart", "BillingPeriodEnd", "BillingCurrency",
    "BillingAccountId", "SubAccountId", "ServiceName", "ServiceCategory", "ServiceProviderName",
    "HostProviderName", "InvoiceIssuerName", "x_Model", "x_Speed", "x_Credits", "x_Measure",
]  # fmt: skip


def _fmt(d: Decimal) -> str:
    with localcontext() as ctx:
        ctx.prec = 60
        return f"{d:f}"


def cost_files(days: list[Day], cfg: CodexConfig) -> tuple[bytes | None, bytes | None, int]:
    """(native USD CSV, credit-estimate CSV, credit rows left unpriced). A stream with no rows is None."""
    usd_rows, credit_rows, unpriced = [], [], 0
    for d in days:
        month_first = d.start.replace(day=1)
        nxt = month_first.replace(
            year=month_first.year + (month_first.month == 12), month=month_first.month % 12 + 1
        )
        common = {
            "ChargeCategory": "Usage", "ChargePeriodStart": d.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ChargePeriodEnd": d.end.strftime("%Y-%m-%dT%H:%M:%SZ"), "BillingPeriodStart": month_first.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "BillingPeriodEnd": nxt.strftime("%Y-%m-%dT%H:%M:%SZ"), "BillingCurrency": "USD", "BillingAccountId": cfg.billing_account_id,
            "ServiceName": "ChatGPT Enterprise and Codex", "ServiceCategory": "AI and Machine Learning", "ServiceProviderName": "OpenAI",
            "HostProviderName": "OpenAI", "InvoiceIssuerName": "OpenAI",
        }  # fmt: skip
        for s in d.slices:
            label = f"{s.model or 'unattributed'}{f' ({s.speed})' if s.speed else ''}"
            base = {**common, "x_Model": s.model or "", "x_Speed": s.speed or ""}
            if s.usd is not None:
                v = _fmt(s.usd)
                usd_rows.append({**base, "BilledCost": v, "EffectiveCost": v, "ListCost": v, "ContractedCost": v,
                                 "ChargeDescription": f"{label} native USD usage", "SubAccountId": f"{cfg.workspace_id}:usd",
                                 "x_Measure": "native_usd"})  # fmt: skip
            if s.credits is not None:
                if s.estimated is None:
                    unpriced += 1  # credits with no dollar estimate are not priced
                    continue
                v = _fmt(s.estimated)
                credit_rows.append({**base, "BilledCost": v, "EffectiveCost": v, "ListCost": v, "ContractedCost": v,
                                    "ChargeDescription": f"{label} credit usage (estimated USD)", "SubAccountId": f"{cfg.workspace_id}:credits",
                                    "x_Credits": _fmt(s.credits), "x_Measure": "credit_estimate"})  # fmt: skip

    def csv_bytes(rows: list[dict]) -> bytes | None:
        if not rows:
            return None
        out = io.StringIO()
        w = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
        return out.getvalue().encode()

    return csv_bytes(usd_rows), csv_bytes(credit_rows), unpriced


# ---- check and pull -----------------------------------------------------------------------------------------


def check(cfg: CodexConfig, client: Client, now: datetime | None = None) -> list[Step]:
    steps = [
        Step(
            "configuration",
            True,
            f"aggregate mode (group=workspace), workspace {cfg.workspace_id}, {cfg.lookback_days} days back",
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
        rows, _ = client.get_all(
            PATH.format(workspace_id=cfg.workspace_id), _params(end - timedelta(days=3), end)
        )
    except SourceError as exc:
        steps.append(Step("access", False, str(exc)))
        return steps
    steps.append(Step("access", True, "the Daily Usage endpoint answered"))
    steps.append(
        Step(
            "data",
            bool(rows),
            f"{len(rows)} workspace day(s) in the last 3 days"
            if rows
            else "no usage in the last 3 days",
        )
    )
    return steps


def pull(
    db: Session,
    tenant_id: uuid.UUID,
    connector_id: uuid.UUID,
    cfg: CodexConfig,
    client: Client,
    now: datetime | None = None,
) -> list[Outcome]:
    out: list[Outcome] = []
    for start, end in windows(cfg, now):
        o = Outcome(f"{start:%Y-%m-%d}..{end:%Y-%m-%d}", "", "")
        out.append(o)
        try:
            rows, _ = client.get_all(
                PATH.format(workspace_id=cfg.workspace_id), _params(start, end)
            )
            days = parse_days(rows)
            if not days:
                o.status, o.detail = "no_data", "no usage in this window"
                continue
            counts = {"inserted": 0, "revised": 0, "unchanged": 0}
            for ob in usage_observations(days, cfg.workspace_id):
                counts[ledger.upsert_aggregate(db, ob)] += 1
            usd, credit, unpriced = cost_files(days, cfg)
            # Finality comes from the window, not from each file's own latest day: a stream with no usage near
            # the window's end must not look settled while its sibling stream is not.
            finality = (
                "final"
                if end + timedelta(days=cfg.final_after_days) <= (now or datetime.now(UTC))
                else "provisional"
            )
            notes, statuses = [f"usage {counts}"], []
            if unpriced:
                notes.append(f"{unpriced} credit row(s) had no dollar estimate and were not priced")
            for label, content, basis in (
                ("usd", usd, "observed"),
                ("credits", credit, "estimated"),
            ):
                if content is None:
                    continue
                name = f"openai:{cfg.workspace_id}:{label}:{start:%Y%m%d}-{end:%Y%m%d}@{hashlib.sha256(content).hexdigest()[:12]}"
                res = import_focus_file(
                    db, tenant_id, connector_id, name, content, declared_version="unknown",
                    finality=finality, now=now, basis=basis,
                )  # fmt: skip
                o.rows += res.rows_imported
                o.superseded += res.superseded
                statuses.append("already_imported" if res.status == "duplicate" else res.status)
                if res.status == "failed":
                    notes.append(f"{label}: {res.error}")
            if not statuses:
                o.status = "no_cost"
            elif "failed" in statuses:
                o.status = "failed"
            elif set(statuses) == {"already_imported"}:
                o.status = "already_imported"
            else:
                o.status = "imported" if "succeeded" in statuses else statuses[0]
            o.detail = "; ".join(notes)
        except (SourceError, credentials.CredentialError) as exc:
            o.status, o.detail = "failed", str(exc)
            break
    return out
