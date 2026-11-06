"""Role assignment with audit and last-admin protection (REQ-003; docs/access-control.md)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .authz import Principal, Role
from .config import Settings
from .db import AuditEvent, RoleAssignment


class RoleError(Exception):
    pass


def _actor(p: Principal) -> str:
    return f"{p.issuer}|{p.subject}"


def _admin_count(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(RoleAssignment).where(RoleAssignment.role == Role.ADMIN)
    )


def _would_lock_out(db: Session, settings: Settings, removing_admin: bool) -> bool:
    """True if the change leaves no day-to-day admin path.

    An IdP admin group is a standing path. The bootstrap identity is break-glass only
    and deliberately does not count.
    """
    return removing_admin and _admin_count(db) <= 1 and not settings.oidc_admin_group


def assign_role(
    db: Session, settings: Settings, actor: Principal, issuer: str, subject: str, role: Role
) -> None:
    current = db.get(RoleAssignment, (issuer, subject))
    if current and current.role == Role.ADMIN and role != Role.ADMIN:
        if _would_lock_out(db, settings, True):
            raise RoleError("cannot demote the last administrator")
    if current:
        current.role = role.value
    else:
        db.add(
            RoleAssignment(
                issuer=issuer, subject=subject, role=role.value, created_by=_actor(actor)
            )
        )
    db.add(
        AuditEvent(
            actor=_actor(actor),
            action="role.assign",
            target=f"{issuer}|{subject}",
            detail={"role": role.value},
        )
    )
    db.commit()


def remove_role(
    db: Session, settings: Settings, actor: Principal, issuer: str, subject: str
) -> None:
    current = db.get(RoleAssignment, (issuer, subject))
    if current is None:
        raise RoleError("no such assignment")
    if current.role == Role.ADMIN and _would_lock_out(db, settings, True):
        raise RoleError("cannot remove the last administrator")
    db.delete(current)
    db.add(AuditEvent(actor=_actor(actor), action="role.remove", target=f"{issuer}|{subject}"))
    db.commit()


def lookup_role(db: Session, issuer: str, subject: str) -> Role | None:
    row = db.get(RoleAssignment, (issuer, subject))
    return Role(row.role) if row else None
