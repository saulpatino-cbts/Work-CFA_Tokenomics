"""Cost-export connectors: AWS Data Exports (S3) and Azure Cost Management exports (Blob Storage).

Both read a FOCUS export from storage the customer already owns, with read-only access, and hand each
billing period's latest run to the FOCUS importer as one logical file. Nothing is written to the
customer's storage and no credential is stored: the platform's own identity is used.

Limits, stated plainly:
- Gzip or plain CSV only. Parquet and zip exports are reported as unsupported with the setting to change.
- A run is held in memory, so there is a size cap (default 200 MB uncompressed). A larger run is
  refused, not truncated. Streaming import is not built.
- Layouts come from vendor documentation and have not been checked against a real export.
"""

from __future__ import annotations

import json
import re
import uuid
import zlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..focus import tables as T
from ..focus.importer import import_focus_file
from .layouts import Run, aws_runs, azure_runs, latest_per_period
from .store import AzureBlobStore, ObjectInfo, ObjectStore, S3Store, StoreError, TooLarge

PROVIDERS = ("aws", "azure")
_COMMON = {
    "provider",
    "prefix",
    "focus_version",
    "lookback_periods",
    "settle_minutes",
    "max_run_mb",
    "allow_partial",
}
_ALLOWED = {
    "aws": _COMMON | {"bucket", "region"},
    "azure": _COMMON | {"account_url", "container"},
}
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_CONTAINER = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
_REGION = re.compile(r"^[a-z]{2}(-[a-z]+)+-\d$")
_AZURE_HOSTS = (
    ".blob.core.windows.net",
    ".blob.core.usgovcloudapi.net",
    ".blob.core.chinacloudapi.cn",
)
# Documented delay before an export stops changing: Azure charges change until the fifth day after the
# period ends (latent charges up to 72 hours after month close); AWS may update the previous period in
# the first two weeks.
FINAL_AFTER_DAYS = {"aws": 14, "azure": 7}
MANIFEST = {
    "aws": {
        "source": "AWS Data Exports to S3 (FOCUS 1.2 or 1.0 with AWS columns, CSV gzip)",
        "measures": ["billed cost", "effective cost", "list cost", "contracted cost"],
        "grain": "usage type per day (per documentation)",
        "delay": "refreshed at least daily; the previous period may change for about two weeks",
        "auth": "ambient AWS identity (instance, task or SSO role), read-only",
        "permissions": ["s3:ListBucket on the export bucket", "s3:GetObject on the export prefix"],
    },
    "azure": {
        "source": "Azure Cost Management export, Cost and usage details (FOCUS), CSV or gzip",
        "measures": ["billed cost", "effective cost", "list cost", "contracted cost"],
        "grain": "usage lines",
        "delay": "available within about 4 hours of a run; charges change until the fifth day after period end",
        "auth": "ambient Azure identity (managed identity), read-only",
        "permissions": ["Storage Blob Data Reader on the export container"],
    },
}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CostExportConfig:
    provider: str
    prefix: str
    bucket: str | None = None
    region: str | None = None
    account_url: str | None = None
    container: str | None = None
    focus_version: str = "1.2"
    lookback_periods: int = 3
    settle_minutes: int = 30
    max_run_mb: int = 200
    allow_partial: bool = False

    @property
    def location(self) -> str:
        where = (
            f"s3://{self.bucket}"
            if self.provider == "aws"
            else f"{self.account_url}/{self.container}"
        )
        return f"{where}/{self.prefix}".rstrip("/")


def parse_scope(provider: str, scope: dict) -> CostExportConfig:
    """Validate connector configuration. Only the documented keys are accepted, so a secret, a SAS
    token or a connection string has nowhere to go."""
    if provider not in PROVIDERS:
        raise ConfigError(f"provider must be one of {', '.join(PROVIDERS)}")
    scope = dict(scope)
    scope.pop("provider", None)
    unknown = sorted(set(scope) - _ALLOWED[provider])
    if unknown:
        raise ConfigError(
            f"unknown setting(s): {', '.join(unknown)}. Credentials are never configured here"
        )
    prefix = str(scope.get("prefix", "")).strip("/")
    if ".." in prefix.split("/") or len(prefix) > 512 or "?" in prefix:
        raise ConfigError("prefix must be a plain path")
    kw: dict = {"provider": provider, "prefix": prefix}
    if provider == "aws":
        bucket = scope.get("bucket")
        if not isinstance(bucket, str) or not _BUCKET.match(bucket):
            raise ConfigError("bucket must be a valid S3 bucket name")
        region = scope.get("region")
        if region is not None and not (isinstance(region, str) and _REGION.match(region)):
            raise ConfigError("region must look like us-east-1")
        kw.update(bucket=bucket, region=region)
    else:
        url, container = scope.get("account_url"), scope.get("container")
        parts = urlsplit(url) if isinstance(url, str) else None
        if (
            not parts
            or parts.scheme != "https"
            or not any((parts.hostname or "").endswith(h) for h in _AZURE_HOSTS)
        ):
            raise ConfigError(
                "account_url must be https://<account>.blob.core.windows.net (or a sovereign cloud equivalent)"
            )
        if (
            parts.query
            or parts.fragment
            or parts.username
            or parts.password
            or parts.path not in ("", "/")
        ):
            raise ConfigError(
                "account_url must be the bare account address: no query string (SAS token), credentials or path"
            )
        if not isinstance(container, str) or not _CONTAINER.match(container):
            raise ConfigError("container must be a valid blob container name")
        kw.update(account_url=f"https://{parts.hostname}", container=container)
    version = scope.get("focus_version", "1.2")
    if version not in ("1.0", "1.1", "1.2", "1.3", "1.4"):
        raise ConfigError("focus_version must be 1.0 to 1.4")
    kw["focus_version"] = version
    for key, lo, hi in (
        ("lookback_periods", 1, 24),
        ("settle_minutes", 0, 1440),
        ("max_run_mb", 1, 2000),
    ):
        v = scope.get(key, getattr(CostExportConfig, key))
        if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
            raise ConfigError(f"{key} must be a whole number from {lo} to {hi}")
        kw[key] = v
    allow = scope.get("allow_partial", False)
    if not isinstance(allow, bool):
        raise ConfigError("allow_partial must be true or false")
    kw["allow_partial"] = allow
    return CostExportConfig(**kw)


def build_store(cfg: CostExportConfig) -> ObjectStore:
    if cfg.provider == "aws":
        return S3Store(cfg.bucket or "", cfg.region)
    return AzureBlobStore(cfg.account_url or "", cfg.container or "")


def _runs(cfg: CostExportConfig, objects: list[ObjectInfo]) -> list[Run]:
    return (aws_runs if cfg.provider == "aws" else azure_runs)(objects, cfg.prefix)


def _list(cfg: CostExportConfig, store: ObjectStore) -> list[ObjectInfo]:
    prefix = cfg.prefix.rstrip("/") + "/" if cfg.prefix else ""
    return list(store.list(prefix))


# ---- check and discover -----------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    name: str
    ok: bool
    message: str


@dataclass
class Discovery:
    selected: list[Run] = field(default_factory=list)
    older_runs_passed_over: int = 0
    outside_lookback: list[str] = field(default_factory=list)


def discover(cfg: CostExportConfig, store: ObjectStore, now: datetime | None = None) -> Discovery:
    """The run to import for each period inside the lookback. Read-only."""
    now = now or datetime.now(UTC)
    runs = _runs(cfg, _list(cfg, store))
    chosen, passed = latest_per_period(runs)
    cutoff = (now - timedelta(days=31 * cfg.lookback_periods)).date()
    d = Discovery(older_runs_passed_over=passed)
    for r in chosen:
        (d.selected if r.period_end >= cutoff else d.outside_lookback).append(r)
    return d


def check(cfg: CostExportConfig, store: ObjectStore, now: datetime | None = None) -> list[Step]:
    """Each step is reported on its own, so a failure says which layer to fix."""
    steps = [Step("configuration", True, f"{cfg.provider} export at {cfg.location}")]
    try:
        objects = _list(cfg, store)
    except StoreError as exc:
        steps.append(Step("access", False, str(exc)))
        return steps
    steps.append(Step("access", True, f"listed the export location ({len(objects)} object(s))"))
    d = discover(cfg, _Fixed(objects), now)
    if not d.selected and not d.outside_lookback:
        steps.append(
            Step(
                "data",
                False,
                "no export runs found at that prefix; check the prefix and that the export has run",
            )
        )
        return steps
    bad = sorted({u for r in d.selected for u in r.unsupported})
    ok_runs = [r for r in d.selected if r.parts]
    if not ok_runs:
        why = (
            f"only {', '.join(bad)} files found: set the export format to CSV with gzip or none"
            if bad
            else "no runs inside the lookback window"
        )
        steps.append(Step("data", False, why))
        return steps
    latest = ok_runs[-1]
    steps.append(
        Step(
            "data",
            True,
            f"{len(ok_runs)} period(s) ready; latest {latest.period} run {latest.run_id or '(in place)'} with {len(latest.parts)} file(s)",
        )
    )
    return steps


class _Fixed:
    """A store over an already-listed set of objects, so check lists the location once."""

    def __init__(self, objects: list[ObjectInfo]):
        self._objects = objects

    def list(self, prefix: str):
        return iter(self._objects)

    def read(self, key: str, limit: int) -> bytes:  # pragma: no cover - never read from here
        raise NotImplementedError


# ---- reading a run ----------------------------------------------------------------------------


class RunError(Exception):
    pass


def _gunzip(raw: bytes, limit: int) -> bytes:
    """Decompress gzip (including concatenated members) without ever holding more than ``limit``."""
    out = bytearray()
    while raw:
        d = zlib.decompressobj(wbits=31)
        try:
            out += d.decompress(raw, limit + 1 - len(out))
        except zlib.error:
            raise RunError("a file is not valid gzip") from None
        if len(out) > limit:
            raise TooLarge("decompressed size")
        if not d.eof:
            raise RunError("a gzip file is truncated")
        raw = d.unused_data
    return bytes(out)


def _header(data: bytes) -> tuple[bytes, bytes]:
    i = data.find(b"\n")
    if i < 0:
        return data.strip(), b""
    return data[: i + 1], data[i + 1 :]


def _norm(h: bytes) -> bytes:
    return h.lstrip(b"\xef\xbb\xbf").strip()


def read_run(store: ObjectStore, run: Run, cap: int) -> bytes:
    """All parts of a run joined into one CSV. Refuses parts whose columns differ, and anything over
    the cap, rather than importing something other than what the cloud produced."""
    if sum(p.size for p in run.parts) > cap:
        raise TooLarge("run")
    header: bytes | None = None
    chunks: list[bytes] = []
    total = 0
    for part in run.parts:
        raw = store.read(part.key, cap)
        data = _gunzip(raw, cap - total) if part.key.lower().endswith(".gz") else raw
        head, body = _header(data)
        if not head.strip():
            continue
        if header is None:
            header = head if head.endswith(b"\n") else head + b"\n"
        elif _norm(head) != _norm(header):
            raise RunError("the files of this run have different columns; nothing was imported")
        if body and not body.endswith(b"\n"):
            body += b"\n"
        total += len(body)
        if total > cap:
            raise TooLarge("run")
        chunks.append(body)
    if header is None:
        raise RunError("the run has no data")
    return header + b"".join(chunks)


# ---- pull --------------------------------------------------------------------------------------


@dataclass
class Outcome:
    period: str
    run_id: str
    status: str  # imported, partial, already_imported, failed_before, deferred, unsupported, too_large, failed
    detail: str = ""
    rows: int = 0
    superseded: int = 0


def _source_name(cfg: CostExportConfig, run: Run) -> str:
    return f"{cfg.provider}:{cfg.location}/{run.period}/{run.run_id or '-'}@{run.fingerprint}"


def pull(
    db: Session,
    tenant_id: uuid.UUID,
    connector_id: uuid.UUID,
    cfg: CostExportConfig,
    store: ObjectStore,
    now: datetime | None = None,
) -> list[Outcome]:
    """Import each ready period once. A run already imported (same files, same etags) is skipped
    without downloading it; a run that failed deterministically is not retried until its files change."""
    now = now or datetime.now(UTC)
    out: list[Outcome] = []
    cap = cfg.max_run_mb * 1_000_000
    for run in discover(cfg, store, now).selected:
        o = Outcome(run.period, run.run_id, "")
        out.append(o)
        if not run.parts:
            o.status, o.detail = (
                "unsupported",
                f"only {', '.join(run.unsupported)} files: set the export format to CSV (gzip or none)",
            )
            continue
        if run.newest > now - timedelta(minutes=cfg.settle_minutes):
            o.status, o.detail = (
                "deferred",
                f"files changed less than {cfg.settle_minutes} minutes ago; will be read on a later run",
            )
            continue
        name = _source_name(cfg, run)
        prior = db.execute(
            select(T.ingestion_runs.c.status, T.ingestion_runs.c.error)
            .where(T.ingestion_runs.c.connector_id == connector_id, T.ingestion_runs.c.source_name == name)
            .order_by(T.ingestion_runs.c.started_at.desc()).limit(1)
        ).first()  # fmt: skip
        if prior and prior.status in ("succeeded", "partial", "running"):
            o.status = "already_imported"
            continue
        if prior and prior.status == "failed":
            o.status, o.detail = (
                "failed_before",
                f"failed earlier and the files have not changed: {prior.error}",
            )
            continue
        try:
            content = read_run(store, run, cap)
        except TooLarge:
            o.status, o.detail = (
                "too_large",
                f"over the {cfg.max_run_mb} MB limit; streaming import is not built (raise max_run_mb or narrow the export)",
            )
            continue
        except (RunError, StoreError) as exc:
            o.status, o.detail = "failed", str(exc)
            continue
        res = import_focus_file(
            db, tenant_id, connector_id, name, content, declared_version=cfg.focus_version,
            final_after_days=FINAL_AFTER_DAYS[cfg.provider], allow_partial=cfg.allow_partial,
            now=now, max_bytes=cap + 1,
        )  # fmt: skip
        o.rows, o.superseded = res.rows_imported, res.superseded
        if res.status == "duplicate":
            o.status, o.detail = "already_imported", "identical content was already imported"
        elif res.status in ("succeeded", "partial"):
            o.status = "imported" if res.status == "succeeded" else "partial"
            if res.rows_rejected:
                o.detail = f"{res.rows_rejected} row(s) rejected"
        else:
            o.status, o.detail = "failed", res.error or "import failed"
    return out


# ---- registration and status ---------------------------------------------------------------------


def create_connector(
    db: Session, tenant_id: uuid.UUID, provider: str, name: str, scope: dict
) -> uuid.UUID:
    """Register an export connector. The configuration is validated first and stored without any secret."""
    cfg = parse_scope(provider, scope)
    stored = {k: v for k, v in cfg.__dict__.items() if v is not None and k != "provider"}
    cid = uuid.uuid4()
    db.execute(
        insert(T.connectors).values(
            id=cid,
            tenant_id=tenant_id,
            provider_key=provider,
            kind="api",
            name=name,
            credential_ref=None,
            scope=stored,
            enabled=True,
        )  # fmt: skip
    )
    db.commit()
    return cid


def load_connector(db: Session, name: str) -> tuple[uuid.UUID, CostExportConfig, bool]:
    row = db.execute(select(T.connectors).where(T.connectors.c.name == name)).first()
    if row is None:
        raise ConfigError(f"no connector named {name!r}")
    if row.provider_key not in PROVIDERS:
        raise ConfigError(f"{name!r} is not a cost-export connector")
    return row.id, parse_scope(row.provider_key, row.scope), row.enabled


def connector_status(db: Session, connector_id: uuid.UUID) -> dict:
    """What the connector has done, from its own records."""
    runs = db.execute(
        text(
            "select status, source_name, row_count, rejected_count, finality, finished_at, error "
            "from ingestion_runs where connector_id = :c order by started_at desc limit 50"
        ),
        {"c": connector_id},
    ).all()
    ok = next((r for r in runs if r.status in ("succeeded", "partial")), None)
    bad = next((r for r in runs if r.status == "failed"), None)
    return {
        "runs": len(runs),
        "last_success": None
        if ok is None
        else {
            "at": ok.finished_at,
            "source": ok.source_name,
            "rows": ok.row_count,
            "finality": ok.finality,
        },
        "last_failure": None if bad is None else {"source": bad.source_name, "error": bad.error},
    }


def scope_json(cfg: CostExportConfig) -> str:
    return json.dumps({k: v for k, v in cfg.__dict__.items() if v is not None}, sort_keys=True)
