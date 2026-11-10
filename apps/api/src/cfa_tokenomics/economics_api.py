"""HTTP API for the economics core (Phase 1 slice 5).

Every route runs in a tenant-scoped session, so PostgreSQL row-level security, not a filter written
here, decides what is visible. Money and quantities are exact decimals: a JSON number that is a
float is refused, send a string or an integer. Reads need ``economics:read``; writes need
``economics:write`` and leave an audit event. Per-application access scoping (ADR 0008 re-scoped)
is not implemented yet: any identity with the role sees every application in its tenant.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import store
from .alloc import runner
from .alloc.runner import AllocationError
from .authz import Permission, Principal, get_principal, require
from .config import Settings, get_settings
from .db import AuditEvent, get_engine
from .econ import scenario as sc
from .econ.node import Node, leaf
from .econ.types import Basis
from .models_econ import Application
from .tenancy import tenant_session

router = APIRouter(prefix="/v1")
_READ = Depends(require(Permission.ECONOMICS_READ))
_WRITE = Depends(require(Permission.ECONOMICS_WRITE))
BasisName = Literal["observed", "estimated", "assumed"]
MAX_SWEEP = 25  # drivers in one tornado request; each costs a full evaluation per bound


def _exact(v: Any) -> Any:
    """Floats are refused: 0.1 as a binary float is not 0.1, and money must be exact."""
    if isinstance(v, float) or isinstance(v, bool):
        raise ValueError("send a decimal as a string or an integer, not a float")
    return v


Num = Annotated[Decimal, BeforeValidator(_exact), Field(allow_inf_nan=False, max_digits=38)]


def tenant_db(
    _authenticated: Principal = Depends(get_principal), settings: Settings = Depends(get_settings)
) -> Iterator[tuple[Session, uuid.UUID]]:
    """Authentication first, so a caller without a token learns nothing about the install."""
    tid = settings.default_tenant_id
    engine = get_engine(settings)
    if tid is None or engine is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "tenant not configured")
    with tenant_session(engine, tid) as db:
        yield db, tid


TenantDb = Annotated[tuple[Session, uuid.UUID], Depends(tenant_db)]


def _actor(p: Principal) -> str:
    return f"{p.issuer}|{p.subject}"


def _audit(db: Session, p: Principal, action: str, target: str, **detail: Any) -> None:
    db.add(AuditEvent(actor=_actor(p), action=action, target=target, detail=detail))
    db.commit()


def _get_app(db: Session, application_id: uuid.UUID) -> Application:
    row = db.get(Application, application_id)
    if row is None:  # absent and another tenant's look the same
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such application")
    return row


def _str(d: Decimal | None) -> str | None:
    return None if d is None else format(d, "f")


# ---- applications -----------------------------------------------------------------------------


class ApplicationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=256)
    currency: str = Field(pattern=r"^[A-Za-z]{3}$")
    owner: str | None = Field(default=None, max_length=256)
    lifecycle: Literal["build", "run", "retire"] = "run"
    initial_investment: Num | None = None
    investment_basis: BasisName | None = None
    amortization_months: int | None = Field(default=None, gt=0, le=1200)


def _app_out(a: Application) -> dict[str, Any]:
    return {
        "id": str(a.id), "name": a.name, "currency": a.currency, "owner": a.owner,
        "lifecycle": a.lifecycle, "initial_investment": _str(a.initial_investment),
        "investment_basis": a.investment_basis, "amortization_months": a.amortization_months,
    }  # fmt: skip


@router.post("/applications", status_code=status.HTTP_201_CREATED)
def create_application(
    body: ApplicationIn, t: TenantDb, actor: Principal = _WRITE
) -> dict[str, Any]:
    db, tid = t
    if (body.initial_investment is None) != (body.investment_basis is None):
        raise HTTPException(422, "initial_investment and investment_basis go together")
    app = store.create_application(db, tid, **body.model_dump())
    _audit(db, actor, "application.create", str(app.id), name=app.name)
    return _app_out(app)


@router.get("/applications")
def list_applications(t: TenantDb, _: Principal = _READ) -> dict[str, Any]:
    db, _tid = t
    rows = db.scalars(select(Application).order_by(Application.name, Application.id))
    return {"applications": [_app_out(a) for a in rows]}


@router.get("/applications/{application_id}")
def get_application(application_id: uuid.UUID, t: TenantDb, _: Principal = _READ) -> dict[str, Any]:
    return _app_out(_get_app(t[0], application_id))


# ---- assumptions ------------------------------------------------------------------------------


class AssumptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Num | None  # null means "unknown", which is not zero
    unit: str = Field(min_length=1, max_length=32)
    basis: BasisName
    rationale: str = Field(min_length=1, max_length=4000)


def _assumption_out(a: Any) -> dict[str, Any]:
    return {
        "key": a.key, "version": a.version, "value": _str(a.value), "unit": a.unit,
        "basis": a.basis, "rationale": a.rationale, "author": a.author,
    }  # fmt: skip


@router.put("/applications/{application_id}/assumptions/{key}")
def put_assumption(
    application_id: uuid.UUID, key: str, body: AssumptionIn, t: TenantDb, actor: Principal = _WRITE
) -> dict[str, Any]:
    """Append a new version. History is never edited, so a change always leaves a trail."""
    db, tid = t
    _get_app(db, application_id)
    if not (0 < len(key) <= 64):
        raise HTTPException(422, "key must be 1 to 64 characters")
    try:
        row = store.add_assumption(
            db, tid, application_id, key, body.value, body.unit, body.basis, body.rationale,
            _actor(actor),
        )  # fmt: skip
    except store.StoreError as exc:
        raise HTTPException(422, str(exc)) from None
    _audit(db, actor, "assumption.set", f"{application_id}/{key}", version=row.version)
    return _assumption_out(row)


@router.get("/applications/{application_id}/assumptions")
def get_assumptions(application_id: uuid.UUID, t: TenantDb, _: Principal = _READ) -> dict[str, Any]:
    db, _tid = t
    _get_app(db, application_id)
    cur = store.current_assumptions(db, application_id)
    return {"assumptions": [_assumption_out(a) for a in cur.values()]}


@router.get("/applications/{application_id}/assumptions/{key}/history")
def assumption_history(
    application_id: uuid.UUID, key: str, t: TenantDb, _: Principal = _READ
) -> dict[str, Any]:
    db, _tid = t
    _get_app(db, application_id)
    rows = store.assumption_history(db, application_id, key)
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such assumption")
    return {"history": [_assumption_out(a) for a in rows]}


# ---- allocation -------------------------------------------------------------------------------


class RuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=256)
    priority: int = Field(ge=0, le=1_000_000)
    method: Literal["direct", "tag", "fixed_percent", "even", "proportional"]
    params: dict[str, Any] = Field(default_factory=dict)
    conditions: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    enabled: bool = True


@router.put("/allocation/rules/{key}")
def put_rule(key: str, body: RuleIn, t: TenantDb, actor: Principal = _WRITE) -> dict[str, Any]:
    """Append a new version of a rule. It is validated; its applications must exist."""
    db, tid = t
    try:
        version = runner.create_rule(db, tid, key, author=_actor(actor), **body.model_dump())
    except (AllocationError, ValueError, KeyError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from None
    _audit(db, actor, "allocation.rule", key, version=version)
    return {"key": key, "version": version}


class DriverIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    value: Num
    basis: BasisName
    source: str = Field(min_length=1, max_length=256)


@router.post("/allocation/rules/{key}/drivers", status_code=status.HTTP_201_CREATED)
def post_driver(key: str, body: DriverIn, t: TenantDb, actor: Principal = _WRITE) -> dict[str, Any]:
    db, tid = t
    if body.period_end <= body.period_start:
        raise HTTPException(422, "period_end must be after period_start")
    _get_app(db, body.application_id)
    try:
        version = runner.add_driver(db, tid, key, author=_actor(actor), **body.model_dump())
    except (ValueError, KeyError, AllocationError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from None
    _audit(db, actor, "allocation.driver", key, version=version)
    return {"rule_key": key, "version": version}


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    window_start: datetime
    window_end: datetime


@router.post("/allocation/runs", status_code=status.HTTP_201_CREATED)
def post_run(body: RunIn, t: TenantDb, actor: Principal = _WRITE) -> dict[str, Any]:
    db, tid = t
    if body.window_end <= body.window_start:
        raise HTTPException(422, "window_end must be after window_start")
    result = runner.run_allocation(db, tid, body.window_start, body.window_end, _actor(actor))
    _audit(db, actor, "allocation.run", str(result.run_id), status=result.status)
    return {
        "status": result.status, "run_id": None if result.run_id is None else str(result.run_id),
        "lines": result.lines, "slices": result.slices, "error": result.error,
    }  # fmt: skip


@router.get("/allocation/summary")
def get_summary(t: TenantDb, _: Principal = _READ) -> dict[str, Any]:
    """Per currency, never combined. Allocated, unallocated (with reasons) and not yet allocated
    are reported separately, with coverage."""
    out = []
    for s in runner.allocation_summary(t[0]):
        out.append(
            {
                "currency": s.currency,
                "total_effective": _str(s.total_effective),
                "allocated_effective": _str(s.allocated_effective),
                "unallocated_effective": _str(s.unallocated_effective),
                "not_yet_allocated_effective": _str(s.not_yet_allocated_effective),
                "coverage": _str(s.coverage),
                "by_method": {k: _str(v) for k, v in s.by_method.items()},
                "unallocated_by_reason": {k: _str(v) for k, v in s.unallocated_by_reason.items()},
                "provider_split_lines": s.provider_split_lines,
            }  # fmt: skip
        )
    return {"summaries": out}


# ---- scenarios and explain --------------------------------------------------------------------


class Q(BaseModel):
    """One driver: a value, how far to trust it, and where it came from. null value = unknown."""

    model_config = ConfigDict(extra="forbid")
    value: Num | None
    basis: BasisName
    source: str | None = Field(default=None, max_length=256)


class ModelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    share: Q
    prices: dict[str, Q] = Field(
        max_length=len(sc.CATEGORIES)
    )  # per million tokens, in the scenario currency


class ScenarioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    currency: str = Field(pattern=r"^[A-Za-z]{3}$")
    users: Q
    adoption: Q
    interactions_per_user: Q
    tokens_per_interaction: dict[str, Q] = Field(min_length=1, max_length=len(sc.CATEGORIES))
    models: list[ModelIn] = Field(min_length=1, max_length=50)
    transactions_per_user: Q
    infra_fixed: Q
    supporting_api: Q
    licence: Q
    ops_hours: Q
    ops_rate: Q
    dev_investment: Q
    dev_months: Q
    infra_variable_per_interaction: Q | None = None
    baseline_hours_per_txn: Q | None = None
    assisted_hours_per_txn: Q | None = None
    loaded_rate: Q | None = None
    realization: Q | None = None
    cashability: Q | None = None
    error_value: Q | None = None
    revenue_value: Q | None = None
    avoided_cost: Q | None = None
    target_margin: Q | None = None
    marketplace_fee_rate: Q | None = None
    marketplace_fixed_fee: Q | None = None
    price: Q | None = None
    save_as: str | None = Field(default=None, max_length=256)
    kind: Literal["baseline", "current", "forecast", "optimized", "customer"] = "current"
    # Tornado: driver path -> [low, high]. Paths as in docs/economics/05, e.g. "users".
    sensitivity: dict[str, tuple[Num, Num]] = Field(default_factory=dict, max_length=MAX_SWEEP)
    sensitivity_output: str = "net_value_capacity"


_UNITS: dict[str, tuple[str, bool]] = {  # field -> (unit, is money)
    "users": ("users", False), "adoption": ("ratio", False),
    "interactions_per_user": ("interactions", False),
    "transactions_per_user": ("transactions", False),
    "infra_fixed": ("money", True), "supporting_api": ("money", True), "licence": ("money", True),
    "ops_hours": ("hours", False), "ops_rate": ("money/hour", True),
    "dev_investment": ("money", True), "dev_months": ("months", False),
    "infra_variable_per_interaction": ("money", True),
    "baseline_hours_per_txn": ("hours", False), "assisted_hours_per_txn": ("hours", False),
    "loaded_rate": ("money/hour", True), "realization": ("ratio", False),
    "cashability": ("ratio", False), "error_value": ("money", True),
    "revenue_value": ("money", True), "avoided_cost": ("money", True),
    "target_margin": ("ratio", False), "marketplace_fee_rate": ("ratio", False),
    "marketplace_fixed_fee": ("money", True), "price": ("money", True),
}  # fmt: skip


def _leaf(key: str, q: Q, unit: str, cur: str | None) -> Node:
    return leaf(key, q.value, unit, Basis(q.basis), cur, source_ref=q.source)


def build_inputs(b: ScenarioIn) -> sc.ScenarioInputs:
    cur = b.currency.upper()
    kw: dict[str, Any] = {"currency": cur}
    for field, (unit, money) in _UNITS.items():
        q = getattr(b, field)
        kw[field] = None if q is None else _leaf(field, q, unit, cur if money else None)
    kw["tokens_per_interaction"] = {
        c: _leaf(f"tpi.{c}", q, "tokens", None) for c, q in b.tokens_per_interaction.items()
    }
    kw["models"] = tuple(
        sc.ModelLine(
            m.name,
            _leaf(f"{m.name}.share", m.share, "ratio", None),
            {
                c: _leaf(f"{m.name}.price.{c}", q, f"{cur}/1M tokens", cur)
                for c, q in m.prices.items()
            },
        )
        for m in b.models
    )
    return sc.ScenarioInputs(**kw)


def _node_out(n: Node) -> dict[str, Any]:
    return {
        "id": n.id, "key": n.key, "value": _str(n.value), "unit": n.unit, "currency": n.currency,
        "status": n.status.value, "note": n.note, "basis": n.basis.value,
        "mix": {"observed": _str(n.mix.observed), "estimated": _str(n.mix.estimated),
                "assumed": _str(n.mix.assumed)},
    }  # fmt: skip


@router.post("/applications/{application_id}/scenarios/evaluate")
def evaluate_scenario(
    application_id: uuid.UUID, body: ScenarioIn, t: TenantDb, actor: Principal = _WRITE
) -> dict[str, Any]:
    """Run the scenario engine. Every figure comes back with its node id (open it with the
    explain route) and its basis mix. The calculation tree is always stored, saved scenario or
    not, because a number that was shown must be explainable.
    """
    db, tid = t
    app = _get_app(db, application_id)
    if body.currency.upper() != app.currency:
        raise HTTPException(422, f"scenario currency must be the application's ({app.currency})")
    try:
        inputs = build_inputs(body)
        results = sc.evaluate(inputs)
        tornado = None
        if body.sensitivity:
            if body.sensitivity_output not in results:
                raise ValueError(f"unknown output {body.sensitivity_output!r}")
            tornado = sc.tornado(inputs, dict(body.sensitivity), body.sensitivity_output)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(422, str(exc)) from None
    for node in results.values():
        store.save_node_tree(db, tid, node)
    scenario_id = None
    if body.save_as:
        drivers = {
            f: (q.value, _UNITS[f][0], q.basis)
            for f in _UNITS if (q := getattr(body, f)) is not None
        }  # fmt: skip
        scenario_id = store.save_scenario(
            db, tid, application_id, body.save_as, body.kind, drivers
        ).id
    _audit(db, actor, "scenario.evaluate", str(application_id), saved=scenario_id is not None)
    return {
        "scenario_id": None if scenario_id is None else str(scenario_id),
        "results": {k: _node_out(n) for k, n in results.items()},
        "tornado": None if tornado is None else [
            {"path": r["path"], "low": _node_out(r["low"]), "high": _node_out(r["high"]),
             "swing": _str(r["swing"])} for r in tornado
        ],
    }  # fmt: skip


@router.get("/explain/{node_id}")
def explain(node_id: str, t: TenantDb, _: Principal = _READ) -> dict[str, Any]:
    """The full tree behind a figure, down to its inputs, verified against its content hash.
    A tampered node is reported as a server error, never silently shown."""
    if not (len(node_id) == 16 and all(c in "0123456789abcdef" for c in node_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such calculation node")
    try:
        root = store.load_node_tree(t[0], node_id)
    except store.TamperedNodeError:
        raise HTTPException(500, "stored calculation failed its integrity check") from None
    except store.StoreError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such calculation node") from None

    def tree(n: Node) -> dict[str, Any]:
        return {
            **_node_out(n), "formula": n.formula_id, "formula_version": n.formula_version,
            "label": n.label, "source_ref": n.source_ref, "inputs": [tree(i) for i in n.inputs],
        }  # fmt: skip

    return tree(root)
