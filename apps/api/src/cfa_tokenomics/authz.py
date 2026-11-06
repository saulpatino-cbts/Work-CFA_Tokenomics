"""Deny-by-default authorization (REQ-003, REQ-004; docs/access-control.md).

The matrix mirrors the *proposed* permission table and still needs owner approval.
Vendor support has no standing permission: it exists only through an active
Assessment grant, which is not implemented yet, so it maps to nothing here.
"""

from dataclasses import dataclass
from enum import StrEnum

from fastapi import Depends, HTTPException, status


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


_MATRIX: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.USER: frozenset(
        {Permission.VIEW_PROVIDERS, Permission.WRITE_RECORDS, Permission.READ_USAGE}
    ),
    Role.READER: frozenset({Permission.VIEW_PROVIDERS, Permission.READ_USAGE}),
}


@dataclass(frozen=True)
class Principal:
    issuer: str  # identity is issuer + subject, never email alone
    subject: str
    role: Role


def is_allowed(principal: Principal, permission: Permission) -> bool:
    return permission in _MATRIX.get(principal.role, frozenset())


def get_principal() -> Principal:
    """Resolve the caller. OIDC verification is NOT implemented yet, so deny everything.

    Tests override this dependency; production must replace it with real token
    validation (issuer, audience, signature, expiry) before any route is exposed.
    """
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication not configured")


def require(permission: Permission):
    def _check(principal: Principal = Depends(get_principal)) -> Principal:
        if not is_allowed(principal, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")
        return principal

    return _check
