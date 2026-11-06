import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from cfa_tokenomics.config import Settings, get_settings
from cfa_tokenomics.main import create_app

ISS, AUD = "https://idp.test", "cfa"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)

SETTINGS = Settings(
    environment="production",
    oidc_issuer=ISS,
    oidc_audience=AUD,
    database_secret_ref="ref",
    oidc_admin_group="cfa-admins",
    oidc_user_group="cfa-users",
    oidc_reader_group="cfa-readers",
    bootstrap_admin=f"{ISS}|break-glass",
)


def tok(key=KEY, alg="RS256", **over):
    claims = {"iss": ISS, "aud": AUD, "sub": "u1", "exp": time.time() + 300, "groups": []}
    claims.update(over)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm=alg)


def client(settings=SETTINGS):
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.key_provider = lambda _t: KEY.public_key()
    return TestClient(app)


def get(token, path="/v1/whoami", c=None):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return (c or client()).get(path, headers=h)


def test_valid_reader_token():
    assert get(tok(groups=["cfa-readers"])).status_code == 200


def test_no_header_is_401():
    assert get(None).status_code == 401


@pytest.mark.parametrize(
    "token",
    [
        tok(exp=time.time() - 10),
        tok(aud="other"),
        tok(iss="https://evil.test"),
        tok(key=OTHER, groups=["cfa-admins"]),
        tok(sub=None),
        "not-a-jwt",
    ],
)
def test_invalid_tokens_are_401(token):
    assert get(token).status_code == 401


def test_alg_none_rejected():
    forged = jwt.encode({"iss": ISS, "aud": AUD, "sub": "u", "exp": time.time() + 99}, None, "none")
    assert get(forged).status_code == 401


def test_hs256_key_confusion_rejected():
    forged = jwt.encode(
        {"iss": ISS, "aud": AUD, "sub": "u", "exp": time.time() + 99, "groups": ["cfa-admins"]},
        "x" * 32,
        "HS256",
    )
    assert get(forged).status_code == 401


def test_valid_token_without_mapped_group_is_403():
    assert get(tok(groups=["something-else"])).status_code == 403


def test_email_claim_grants_nothing():
    assert get(tok(email="admin@example.com", groups=[])).status_code == 403


def test_bootstrap_admin_by_issuer_and_subject():
    assert get(tok(sub="break-glass")).status_code == 200
    # same subject from a different issuer must not match
    c = client(SETTINGS.model_copy(update={"oidc_issuer": "https://other.test"}))
    assert get(tok(sub="break-glass", iss="https://other.test"), c=c).status_code == 403


def test_no_issuer_configured_denies():
    c = client(Settings(environment="development"))
    assert get(tok(groups=["cfa-admins"]), c=c).status_code == 401


def test_production_requires_an_admin_path():
    with pytest.raises(ValueError):
        Settings(
            environment="production",
            oidc_issuer=ISS,
            oidc_audience=AUD,
            database_secret_ref="r",
        )
