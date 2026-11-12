"""Configuration validation (REQ-008, REQ-009).

Secrets are never configuration values: only *references* (names/ARNs/URIs of a
customer-controlled secret store) may be set here (REQ-002).
"""

import uuid
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CFA_", extra="ignore")

    environment: Literal["development", "production"] = "production"
    # Reference to the customer's database secret, not a connection string with a password.
    database_secret_ref: str | None = None
    # Injected at runtime by the platform from the customer's secret store; never committed.
    database_url: SecretStr | None = None
    oidc_issuer: str | None = Field(default=None, description="Customer OIDC issuer URL")
    oidc_audience: str | None = None
    # Public client id of the browser app (authorization code + PKCE; no client secret).
    oidc_client_id: str | None = None
    # Single-tenant installs: the tenant every authenticated user acts in
    # (ADR 0011 working assumption 1).
    default_tenant_id: uuid.UUID | None = None
    # Dev and test only. Readiness fails when the database role can bypass row-level security
    # (superuser or BYPASSRLS), because tenant isolation would then be silently off.
    allow_rls_bypass: bool = False
    # Directory of the built web app, served same-origin. Unset means API only.
    web_dir: str | None = None
    oidc_jwks_uri: str | None = Field(default=None, description="Override; else OIDC discovery")
    # Role mapping from a customer-controlled claim. No match means no access.
    oidc_roles_claim: str = "groups"
    oidc_admin_group: str | None = None
    oidc_finance_group: str | None = None
    # First-admin / IdP-outage recovery: "<issuer>|<subject>", set by the customer operator.
    bootstrap_admin: str | None = None

    @model_validator(mode="after")
    def _require_identity_in_production(self) -> "Settings":
        if self.environment == "production":
            missing = [
                name
                for name in ("oidc_issuer", "oidc_audience", "database_secret_ref")
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(
                    "production requires: " + ", ".join(f"CFA_{m.upper()}" for m in missing)
                )
            if not (self.oidc_issuer or "").startswith("https://"):
                raise ValueError("CFA_OIDC_ISSUER must be an https:// URL")
            if self.oidc_jwks_uri and not self.oidc_jwks_uri.startswith("https://"):
                raise ValueError("CFA_OIDC_JWKS_URI must be an https:// URL")
            if not (self.bootstrap_admin or self.oidc_admin_group):
                raise ValueError(
                    "production needs CFA_OIDC_ADMIN_GROUP or CFA_BOOTSTRAP_ADMIN "
                    "so a first administrator can exist"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
