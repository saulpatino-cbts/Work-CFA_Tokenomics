"""Configuration validation (REQ-008, REQ-009).

Secrets are never configuration values: only *references* (names/ARNs/URIs of a
customer-controlled secret store) may be set here (REQ-002).
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CFA_", extra="ignore")

    environment: Literal["development", "production"] = "production"
    # Reference to the customer's database secret, not a connection string with a password.
    database_secret_ref: str | None = None
    oidc_issuer: str | None = Field(default=None, description="Customer OIDC issuer URL")
    oidc_audience: str | None = None

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
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
