from fastapi.testclient import TestClient

from cfa_tokenomics.config import Settings, get_settings
from cfa_tokenomics.main import create_app


def test_healthz_leaks_nothing():
    r = TestClient(create_app()).get("/healthz")
    assert r.status_code == 200 and set(r.json()) == {"status", "version"}


def test_readyz():
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(environment="development")
    assert TestClient(app).get("/readyz").json() == {
        "status": "ready",
        "database": "not_configured",
    }
