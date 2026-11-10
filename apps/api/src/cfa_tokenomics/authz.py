"""Deny-by-default authorization (REQ-003, REQ-004; docs/access-control.md).

The matrix mirrors the *proposed* permission table and still needs owner approval.
Vendor support has no standing permission: it exists only through an active
Assessment grant, which is not implemented yet, so it maps to nothing here.
"""

from dataclasses import dataclass
from enum import StrEnum

from fastapi import Depends, HTTPException, Request, status

from .config import Settings, get_settings


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"
    READER = "reader"


class Permission(StrEnum):
    MANAGE_IDENTITY = "identity:manage"
    MANAGE_PROVIDERS = "providers:manage"
    VIEW_PROVIDERS = "providers:view"
    WRITE_RECORDS = "records:write"
    READ_USAGE = "usage:read"
    EXPORT_IMPORT = "data:export_import"
    MANAGE_ASSESSMENT = "assessment:manage"
    ECONOMICS_READ = "economics:read"
    ECONOMICS_WRITE = "economics:write"


_MATRIX: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.USER: frozenset(
        {
            Permission.VIEW_PROVIDERS,
            Permission.WRITE_RECORDS,
            Permission.READ_USAGE,
            Permission.ECONOMICS_READ,
            Permission.ECONOMICS_WRITE,
        }
    ),
    Role.READER: frozenset(
        {Permission.VIEW_PROVIDERS, Permission.READ_USAGE, Permission.ECONOMICS_READ}
    ),
}


@dataclass(frozen=True)
class Principal:
    issuer: str  # identity is issuer + subject, never email alone
    subject: str
    role: Role


def is_allowed(principal: Principal, permission: Permission) -> bool:
    return permission in _MATRIX.get(principal.role, frozenset())


_RANK = {Role.READER: 1, Role.USER: 2, Role.ADMIN: 3}


def _highest(*roles: Role | None) -> Role | None:
    present = [r for r in roles if r is not None]
    return max(present, key=_RANK.__getitem__) if present else None


def _stored_role(settings: Settings, claims: dict) -> Role | None:
    from sqlalchemy.orm import Session

    from .db import RoleAssignment, get_engine

    engine = get_engine(settings)
    if engine is None:
        return None
    with Session(engine) as db:
        row = db.get(RoleAssignment, (claims["iss"], claims["sub"]))
        return Role(row.role) if row else None


def get_principal(request: Request, settings: Settings = Depends(get_settings)) -> Principal:
    """Verify the bearer token and map it to a role. Anything else is a denial."""
    from . import auth

    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token or not settings.oidc_issuer:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    provider = getattr(request.app.state, "key_provider", None) or auth.jwks_key_provider(settings)
    request.app.state.key_provider = provider
    try:
        claims = auth.verify_token(token, settings, provider)
    except auth.AuthError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from None
    role = _highest(auth.map_role(claims, settings), _stored_role(settings, claims))
    if role is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no role mapped")
    return Principal(issuer=claims["iss"], subject=claims["sub"], role=role)


def require(permission: Permission):
    def _check(principal: Principal = Depends(get_principal)) -> Principal:
        if not is_allowed(principal, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")
        return principal

    return _check
