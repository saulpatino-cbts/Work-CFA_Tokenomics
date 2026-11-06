from fastapi.testclient import TestClient

from cfa_tokenomics.config import Settings, get_settings
from cfa_tokenomics.main import create_app


def _client(**kw):
    app = create_app()
    settings = Settings(environment="development", **kw)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_public_config_exposes_only_public_values():
    c = _client(
        oidc_issuer="https://idp.test",
        oidc_client_id="web",
        oidc_audience="cfa",
        database_secret_ref="secret-ref",
    )
    body = c.get("/config.json").json()
    assert body == {
        "oidc_issuer": "https://idp.test",
        "oidc_client_id": "web",
        "oidc_audience": "cfa",
    }
    assert "secret" not in str(body)


def test_security_headers_on_every_response():
    r = _client().get("/healthz")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    csp = r.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp and "script-src 'self'" in csp


def test_csp_allows_the_configured_issuer_only():
    r = _client(oidc_issuer="https://idp.test/realm").get("/healthz")
    assert "connect-src 'self' https://idp.test;" in r.headers["content-security-policy"]


def test_config_with_nothing_set_is_null_not_an_error():
    assert _client().get("/config.json").json()["oidc_issuer"] is None


def test_built_web_app_is_served_and_api_routes_are_not_shadowed(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<!doctype html><title>app</title>")
    monkeypatch.setenv("CFA_ENVIRONMENT", "development")
    monkeypatch.setenv("CFA_WEB_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        c = TestClient(create_app())
        assert "<title>app</title>" in c.get("/").text
        assert c.get("/healthz").json()["status"] == "ok"
        assert c.get("/config.json").status_code == 200
        assert c.get("/v1/whoami").status_code == 401  # API still enforces auth
    finally:
        get_settings.cache_clear()
