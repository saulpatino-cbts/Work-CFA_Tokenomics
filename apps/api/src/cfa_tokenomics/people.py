"""People: pseudonyms to display names, and what administrators see (ADR 0013).

Usage and cost rows hold only keyed pseudonyms (``privacy.Pseudonymizer``). The ``people`` table is
the single place a pseudonym maps to a name. A tenant setting, ``person_display``, decides whether
the product shows pseudonyms (the default) or names. Showing names never writes a name into the
cost or usage data, and every change of the setting and every lookup of names is audited. The
audit entry records how many names were shown and never the names themselves.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .authz import Principal
from .db import AuditEvent
from .models_econ import Person, Tenant
from .privacy import Pseudonymizer

Display = Literal["pseudonym", "name"]
SOURCES = ("manual", "entra", "google")
MAX_NAME = 256
MAX_LOOKUP = 500


class PeopleError(ValueError):
    pass


def _actor(p: Principal) -> str:
    return f"{p.issuer}|{p.subject}"


def get_display(db: Session, tenant_id: uuid.UUID) -> Display:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise PeopleError("no such tenant")
    return "name" if tenant.person_display == "name" else "pseudonym"


def set_display(db: Session, actor: Principal, tenant_id: uuid.UUID, mode: object) -> Display:
    """Choose what the product shows. Anything but the exact words is refused."""
    if mode not in ("pseudonym", "name"):
        raise PeopleError("display must be 'pseudonym' or 'name'")
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise PeopleError("no such tenant")
    previous = tenant.person_display
    tenant.person_display = mode
    db.add(
        AuditEvent(
            actor=_actor(actor),
            action="people.display",
            target=str(tenant_id),
            detail={"from": previous, "to": mode},
        )
    )
    db.commit()
    return mode  # type: ignore[return-value]


def upsert_people(
    db: Session,
    actor: Principal,
    tenant_id: uuid.UUID,
    pz: Pseudonymizer,
    rows: Iterable[tuple[str, str]],
    source: str = "manual",
) -> dict[str, int]:
    """Record names for identifiers. The identifier is pseudonymized and then dropped; only the
    pseudonym and the name are stored. All rows or none: one bad row refuses the whole batch."""
    if source not in SOURCES:
        raise PeopleError(f"source must be one of {', '.join(SOURCES)}")
    prepared: dict[str, str] = {}
    for line, (identifier, name) in enumerate(rows, 1):
        name = (name or "").strip()
        if not name or len(name) > MAX_NAME:
            raise PeopleError(f"row {line}: the name must be 1 to {MAX_NAME} characters")
        try:
            prepared[pz.pseudonym(identifier or "")] = name
        except ValueError:
            raise PeopleError(f"row {line}: the identifier is empty") from None
    added = updated = 0
    now = datetime.now(UTC)
    for pseudonym, name in prepared.items():
        row = db.get(Person, (tenant_id, pseudonym))
        if row is None:
            db.add(
                Person(
                    tenant_id=tenant_id,
                    pseudonym=pseudonym,
                    display_name=name,
                    source=source,
                    updated_at=now,
                )
            )
            added += 1
        elif (row.display_name, row.source) != (name, source):
            row.display_name, row.source, row.updated_at = name, source, now
            updated += 1
    db.add(
        AuditEvent(
            actor=_actor(actor),
            action="people.import",
            target=str(tenant_id),
            detail={"source": source, "added": added, "updated": updated},
        )
    )
    db.commit()
    return {"added": added, "updated": updated, "unchanged": len(prepared) - added - updated}


def resolve(
    db: Session, actor: Principal, tenant_id: uuid.UUID, pseudonyms: list[str]
) -> dict[str, str]:
    """What to show for each pseudonym. In pseudonym mode that is the pseudonym itself and nothing
    is looked up. In name mode a known pseudonym becomes its name and an unknown one stays a
    pseudonym (shown as unattributed by the screens), never dropped. One audit entry per call."""
    if len(pseudonyms) > MAX_LOOKUP:
        raise PeopleError(f"look up at most {MAX_LOOKUP} people at once")
    shown = {p: p for p in pseudonyms}
    if get_display(db, tenant_id) != "name" or not pseudonyms:
        return shown
    rows = db.execute(
        select(Person.pseudonym, Person.display_name).where(
            Person.tenant_id == tenant_id, Person.pseudonym.in_(set(pseudonyms))
        )
    ).all()
    for pseudonym, name in rows:
        shown[pseudonym] = name
    db.add(
        AuditEvent(
            actor=_actor(actor),
            action="people.resolve",
            target=str(tenant_id),
            detail={"asked": len(shown), "shown_as_names": len(rows)},
        )
    )
    db.commit()
    return shown
