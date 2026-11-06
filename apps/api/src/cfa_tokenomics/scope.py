"""Account scope: which (provider, account) pairs an identity may read (ADR 0008)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .authz import Principal, Role
from .db import AccountGrant, AuditEvent


def allowed_accounts(db: Session, principal: Principal) -> list[tuple[str, str]] | None:
    """None = unrestricted (admin). Otherwise the explicit grants; none means no access."""
    if principal.role is Role.ADMIN:
        return None
    rows = db.execute(
        select(AccountGrant.provider, AccountGrant.account).where(
            AccountGrant.issuer == principal.issuer, AccountGrant.subject == principal.subject
        )
    ).all()
    return [(p, a) for p, a in rows]


def grant(
    db: Session,
    actor: Principal,
    issuer: str,
    subject: str,
    provider: str,
    account: str,
) -> None:
    if db.get(AccountGrant, (issuer, subject, provider, account)) is None:
        db.add(
            AccountGrant(
                issuer=issuer,
                subject=subject,
                provider=provider,
                account=account,
                created_by=f"{actor.issuer}|{actor.subject}",
            )
        )
    db.add(
        AuditEvent(
            actor=f"{actor.issuer}|{actor.subject}",
            action="grant.add",
            target=f"{issuer}|{subject}",
            detail={"provider": provider, "account": account},
        )
    )
    db.commit()


def revoke(
    db: Session, actor: Principal, issuer: str, subject: str, provider: str, account: str
) -> bool:
    row = db.get(AccountGrant, (issuer, subject, provider, account))
    if row is None:
        return False
    db.delete(row)
    db.add(
        AuditEvent(
            actor=f"{actor.issuer}|{actor.subject}",
            action="grant.remove",
            target=f"{issuer}|{subject}",
            detail={"provider": provider, "account": account},
        )
    )
    db.commit()
    return True
