"""OIDC bearer-token verification and role mapping (REQ-002, REQ-003).

Validates signature, issuer, audience, expiry and presence of ``sub``. Only
asymmetric algorithms are accepted, so ``none`` and HS* key-confusion tokens are
rejected. Identity is issuer + subject, never email.
"""

from collections.abc import Callable
from typing import Any

import httpx
import jwt

from .config import Settings

ALLOWED_ALGS = ["RS256", "RS384", "RS512", "ES256", "ES384"]

KeyProvider = Callable[[str], Any]  # token -> signing key


class AuthError(Exception):
    """Token is missing, malformed, or fails validation."""


def jwks_key_provider(settings: Settings) -> KeyProvider:
    """Resolve signing keys from the customer's IdP (discovery unless a JWKS URI is set)."""
    state: dict[str, jwt.PyJWKClient] = {}

    def _client() -> jwt.PyJWKClient:
        if "c" not in state:
            uri = settings.oidc_jwks_uri
            if not uri:
                issuer = (settings.oidc_issuer or "").rstrip("/")
                resp = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=5.0)
                resp.raise_for_status()
                uri = resp.json()["jwks_uri"]
            state["c"] = jwt.PyJWKClient(uri, timeout=5)
        return state["c"]

    def _key(token: str) -> Any:
        return _client().get_signing_key_from_jwt(token).key

    return _key


def verify_token(token: str, settings: Settings, key_provider: KeyProvider) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            key=key_provider(token),
            algorithms=ALLOWED_ALGS,
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except Exception as exc:  # any failure, including key lookup, is a denial
        raise AuthError(type(exc).__name__) from exc
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise AuthError("bad sub")
    return claims


def map_role(claims: dict[str, Any], settings: Settings):
    """Return the highest mapped Role, or None (deny). Imported lazily to avoid a cycle."""
    from .authz import Role

    if settings.bootstrap_admin and settings.bootstrap_admin == f"{claims['iss']}|{claims['sub']}":
        return Role.ADMIN
    raw = claims.get(settings.oidc_roles_claim, [])
    groups = {raw} if isinstance(raw, str) else set(raw) if isinstance(raw, list) else set()
    for role, group in (
        (Role.ADMIN, settings.oidc_admin_group),
        (Role.USER, settings.oidc_user_group),
        (Role.READER, settings.oidc_reader_group),
    ):
        if group and group in groups:
            return role
    return None
