"""Repository functions for the economics core. Every function expects a session from
``tenancy.tenant_session`` so that row-level security scopes it to one tenant."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .econ.node import Node, Status
from .econ.types import BasisMix
from .models_econ import (
    Application,
    CalcEdgeRow,
    CalcNodeRow,
    PriceBook,
    PriceEntry,
    Scenario,
    ScenarioDriver,
    Tenant,
    ValueAssumption,
)
from .tenancy import tenant_session


class StoreError(Exception):
    pass


class PriceOverlapError(StoreError):
    pass


class TamperedNodeError(StoreError):
    """A stored calculation node no longer matches its content hash."""


def create_tenant(engine: Engine, name: str, base_currency: str, setup=None) -> uuid.UUID:
    """Create a tenant. The session is scoped to the new id, which is what lets the insert pass
    the row-level security check; there is no way to create a tenant inside another one."""
    tid = uuid.uuid4()
    with tenant_session(engine, tid, setup) as db:
        db.add(Tenant(id=tid, name=name, base_currency=base_currency.upper()))
        db.commit()
    return tid


def create_application(
    db: Session,
    tenant_id: uuid.UUID,
    name: str,
    currency: str,
    *,
    owner: str | None = None,
    lifecycle: str = "run",
    initial_investment: Decimal | None = None,
    investment_basis: str | None = None,
    amortization_months: int | None = None,
    business_unit_id: uuid.UUID | None = None,
) -> Application:
    app = Application(
        tenant_id=tenant_id, name=name, currency=currency.upper(), owner=owner, lifecycle=lifecycle,
        initial_investment=initial_investment, investment_basis=investment_basis,
        amortization_months=amortization_months, business_unit_id=business_unit_id,
    )  # fmt: skip
    db.add(app)
    db.commit()
    return app


def add_assumption(
    db: Session,
    tenant_id: uuid.UUID,
    application_id: uuid.UUID,
    key: str,
    value: Decimal | None,
    unit: str,
    basis: str,
    rationale: str,
    author: str,
) -> ValueAssumption:
    """Append a new version of an assumption. History is never edited. A rationale is required
    (no silent defaults), enforced by the database as well."""
    if not rationale.strip():
        raise StoreError("an assumption needs a rationale")
    latest = db.scalar(
        select(func.max(ValueAssumption.version)).where(
            ValueAssumption.application_id == application_id, ValueAssumption.key == key
        )
    )
    row = ValueAssumption(
        tenant_id=tenant_id, application_id=application_id, key=key, value=value, unit=unit,
        basis=basis, rationale=rationale, author=author, version=(latest or 0) + 1,
    )  # fmt: skip
    db.add(row)
    db.commit()
    return row


def current_assumptions(db: Session, application_id: uuid.UUID) -> dict[str, ValueAssumption]:
    """The latest version of each assumption key."""
    rows = db.scalars(
        select(ValueAssumption)
        .where(ValueAssumption.application_id == application_id)
        .order_by(ValueAssumption.key, ValueAssumption.version)
    ).all()
    return {r.key: r for r in rows}  # later versions overwrite earlier ones


def assumption_history(db: Session, application_id: uuid.UUID, key: str) -> list[ValueAssumption]:
    return list(
        db.scalars(
            select(ValueAssumption)
            .where(ValueAssumption.application_id == application_id, ValueAssumption.key == key)
            .order_by(ValueAssumption.version)
        )
    )


def add_price_entry(
    db: Session,
    tenant_id: uuid.UUID,
    book: PriceBook,
    provider: str,
    model_key: str,
    measure: str,
    unit_price: Decimal,
    currency: str,
    effective_from: datetime,
    effective_to: datetime | None = None,
    per_quantity: Decimal = Decimal(1_000_000),
    inclusion_rule: str | None = None,
) -> PriceEntry:
    """Add a price. A price book never holds two prices for the same measure at the same time, and a
    price must be in the book's currency (no silent conversion)."""
    if currency.upper() != book.currency:
        raise StoreError(f"price currency {currency} differs from the book's {book.currency}")
    clash = select(PriceEntry.id).where(
        PriceEntry.price_book_id == book.id,
        PriceEntry.provider == provider,
        PriceEntry.model_key == model_key,
        PriceEntry.measure == measure,
        (PriceEntry.effective_to.is_(None)) | (PriceEntry.effective_to > effective_from),
    )
    if effective_to is not None:
        clash = clash.where(PriceEntry.effective_from < effective_to)
    if db.scalar(clash.limit(1)) is not None:
        raise PriceOverlapError("a price already covers part of that period")
    row = PriceEntry(
        tenant_id=tenant_id, price_book_id=book.id, provider=provider, model_key=model_key,
        measure=measure, unit_price=unit_price, per_quantity=per_quantity,
        currency=currency.upper(),
        effective_from=effective_from, effective_to=effective_to, inclusion_rule=inclusion_rule,
    )  # fmt: skip
    db.add(row)
    db.commit()
    return row


def price_at(
    db: Session, book_id: uuid.UUID, provider: str, model_key: str, measure: str, at: datetime
) -> PriceEntry | None:
    return db.scalar(
        select(PriceEntry).where(
            PriceEntry.price_book_id == book_id,
            PriceEntry.provider == provider,
            PriceEntry.model_key == model_key,
            PriceEntry.measure == measure,
            PriceEntry.effective_from <= at,
            (PriceEntry.effective_to.is_(None)) | (PriceEntry.effective_to > at),
        )
    )


def save_scenario(
    db: Session,
    tenant_id: uuid.UUID,
    application_id: uuid.UUID,
    name: str,
    kind: str,
    drivers: dict[str, tuple[Decimal | None, str, str]],
    base_scenario_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
) -> Scenario:
    """Store a scenario and its drivers as ``key -> (value, unit, basis)``."""
    sc = Scenario(
        tenant_id=tenant_id, application_id=application_id, name=name, kind=kind,
        base_scenario_id=base_scenario_id, customer_id=customer_id,
    )  # fmt: skip
    db.add(sc)
    db.flush()
    for key, (value, unit, basis) in drivers.items():
        db.add(
            ScenarioDriver(
                tenant_id=tenant_id,
                scenario_id=sc.id,
                driver_key=key,
                value=value,
                unit=unit,
                basis=basis,
            )
        )
    db.commit()
    return sc


# ---- calculation nodes: persistence with tamper detection -------------------------------------


def save_node_tree(db: Session, tenant_id: uuid.UUID, root: Node) -> int:
    """Persist a node and everything beneath it. Idempotent: nodes are content-addressed.

    Returns the number of distinct nodes in the tree."""
    seen: dict[str, Node] = {}
    for n in root.walk():
        seen.setdefault(n.id, n)
    for n in seen.values():
        db.execute(
            insert(CalcNodeRow)
            .values(
                tenant_id=tenant_id,
                id=n.id,
                key=n.key,
                formula_id=n.formula_id,
                formula_version=n.formula_version,
                value=n.value,
                unit=n.unit,
                currency=n.currency,
                mix_observed=n.mix.observed,
                mix_estimated=n.mix.estimated,
                mix_assumed=n.mix.assumed,
                status=n.status.value,
                note=n.note,
                label=n.label,
                source_ref=n.source_ref,
            )
            .on_conflict_do_nothing(index_elements=["tenant_id", "id"])
        )
    for n in seen.values():
        for pos, child in enumerate(n.inputs):
            db.execute(
                insert(CalcEdgeRow)
                .values(tenant_id=tenant_id, parent_id=n.id, position=pos, child_id=child.id)
                .on_conflict_do_nothing(index_elements=["tenant_id", "parent_id", "position"])
            )
    db.commit()
    return len(seen)


def load_node_tree(db: Session, root_id: str) -> Node:
    """Rebuild a stored tree and verify every node against its content hash. A node that was edited
    or rounded after it was written raises ``TamperedNodeError``."""
    ids = db.execute(
        text(
            "with recursive r(id) as (select cast(:root as varchar) union "
            "select e.child_id from calculation_edges e join r on e.parent_id = r.id) "
            "select id from r"
        ),
        {"root": root_id},
    ).scalars().all()  # fmt: skip
    rows = {r.id: r for r in db.scalars(select(CalcNodeRow).where(CalcNodeRow.id.in_(ids)))}
    if root_id not in rows:  # absent or another tenant's: the two look the same on purpose
        raise StoreError("no such calculation node")
    edges: dict[str, list[str]] = {}
    for e in db.scalars(select(CalcEdgeRow).where(CalcEdgeRow.parent_id.in_(ids)).order_by(
        CalcEdgeRow.parent_id, CalcEdgeRow.position
    )):  # fmt: skip
        edges.setdefault(e.parent_id, []).append(e.child_id)
    built: dict[str, Node] = {}

    def build(nid: str) -> Node:
        if nid in built:
            return built[nid]
        r = rows.get(nid)
        if r is None:
            raise StoreError(f"missing calculation node {nid}")
        kids = tuple(build(c) for c in edges.get(nid, []))
        node = Node(
            key=r.key, formula_id=r.formula_id, formula_version=r.formula_version, value=r.value,
            unit=r.unit, currency=r.currency,
            mix=BasisMix(r.mix_observed, r.mix_estimated, r.mix_assumed), inputs=kids,
            label=r.label, source_ref=r.source_ref, status=Status(r.status), note=r.note,
        )  # fmt: skip
        if node.id != nid:
            raise TamperedNodeError(f"calculation node {nid} does not match its content hash")
        built[nid] = node
        return node

    return build(root_id)
