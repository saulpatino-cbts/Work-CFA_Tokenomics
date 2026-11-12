"""One place that knows which connector kinds exist, so the admin commands stay generic.

Each kind turns a stored connector row into something runnable, reports its readiness step by step,
lists what a run would read without reading it, and pulls. Credentials and storage handles are built here
at run time and never stored.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..focus import tables as T
from . import anthropic as anth
from . import costexport as cx


class ConfigError(cx.ConfigError):
    pass


@dataclass(frozen=True)
class Row:
    id: uuid.UUID
    provider_key: str
    scope: dict
    credential_ref: str | None
    enabled: bool


class Kind(Protocol):
    def create(self, db: Session, tenant_id: uuid.UUID, name: str, scope: dict) -> uuid.UUID: ...
    def prepare(self, row: Row) -> Any: ...
    def check(self, prepared: Any, now: datetime | None = None) -> list[cx.Step]: ...
    def dry_run(self, prepared: Any, now: datetime | None = None) -> list[str]: ...
    def pull(
        self,
        db: Session,
        tenant_id: uuid.UUID,
        row: Row,
        prepared: Any,
        now: datetime | None = None,
    ) -> list[cx.Outcome]: ...


class CostExportKind:
    def __init__(self, provider: str):
        self.provider = provider

    def create(self, db, tenant_id, name, scope):
        return cx.create_connector(db, tenant_id, self.provider, name, scope)

    def prepare(self, row):
        cfg = cx.parse_scope(row.provider_key, row.scope)
        return cfg, cx.build_store(cfg)

    def check(self, prepared, now=None):
        cfg, store = prepared
        return cx.check(cfg, store, now)

    def dry_run(self, prepared, now=None):
        cfg, store = prepared
        out = []
        for r in cx.discover(cfg, store, now).selected:
            out.append(
                f"would read {r.period} run {r.run_id or '(in place)'}: {len(r.parts)} file(s)"
            )
        return out

    def pull(self, db, tenant_id, row, prepared, now=None):
        cfg, store = prepared
        return cx.pull(db, tenant_id, row.id, cfg, store, now)


class AnthropicKind:
    def create(self, db, tenant_id, name, scope):
        return anth.create_connector(db, tenant_id, name, scope)

    def prepare(self, row):
        cfg = anth.parse_scope(row.scope, row.credential_ref)
        return cfg, anth.build_client(cfg)

    def check(self, prepared, now=None):
        cfg, client = prepared
        return anth.check(cfg, client, now)

    def dry_run(self, prepared, now=None):
        cfg, _client = prepared
        return [
            f"would read {a:%Y-%m-%d} to {b:%Y-%m-%d} (usage and cost)"
            for a, b in anth.windows(cfg, now)
        ]

    def pull(self, db, tenant_id, row, prepared, now=None):
        cfg, client = prepared
        return anth.pull(db, tenant_id, row.id, cfg, client, now)


KINDS: dict[str, Kind] = {
    "aws": CostExportKind("aws"),
    "azure": CostExportKind("azure"),
    "anthropic": AnthropicKind(),
}


def kind_for(provider_key: str) -> Kind:
    try:
        return KINDS[provider_key]
    except KeyError:
        raise ConfigError(
            f"unknown connector provider {provider_key!r}; expected one of {', '.join(KINDS)}"
        ) from None


def load_row(db: Session, name: str) -> Row:
    r = db.execute(select(T.connectors).where(T.connectors.c.name == name)).first()
    if r is None:
        raise ConfigError(f"no connector named {name!r}")
    kind_for(r.provider_key)
    return Row(r.id, r.provider_key, r.scope, r.credential_ref, r.enabled)
