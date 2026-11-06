import pytest
from pydantic import ValidationError

from cfa_tokenomics.config import Settings


def test_production_requires_identity_and_database_ref(monkeypatch):
    for k in ("CFA_OIDC_ISSUER", "CFA_OIDC_AUDIENCE", "CFA_DATABASE_SECRET_REF"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValidationError):
        Settings(environment="production")


def test_production_rejects_non_https_issuer():
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            oidc_issuer="http://idp.test",
            oidc_audience="a",
            database_secret_ref="ref",
        )


def test_valid_production_config():
    s = Settings(
        environment="production",
        oidc_issuer="https://idp.test",
        oidc_audience="a",
        database_secret_ref="ref",
    )
    assert s.environment == "production"


def test_development_needs_nothing():
    assert Settings(environment="development").oidc_issuer is None
