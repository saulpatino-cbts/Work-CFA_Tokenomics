import pytest
from fastapi.testclient import TestClient

from cfa_tokenomics.authz import Permission, Principal, Role, get_principal, is_allowed
from cfa_tokenomics.config import Settings, get_settings
from cfa_tokenomics.main import create_app


def _client(role: Role | None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(environment="development")
    if role is not None:
        app.dependency_overrides[get_principal] = lambda: Principal("https://idp.test", "s1", role)
    return TestClient(app)


def test_unauthenticated_is_denied():
    assert _client(None).get("/v1/usage").status_code == 401


@pytest.mark.parametrize("role", list(Role))
def test_roles_with_usage_read_allowed(role):
    assert _client(role).get("/v1/usage").status_code == 200


@pytest.mark.parametrize("role", [Role.USER, Role.READER])
@pytest.mark.parametrize(
    "perm",
    [
        Permission.MANAGE_IDENTITY,
        Permission.MANAGE_PROVIDERS,
        Permission.EXPORT_IMPORT,
        Permission.MANAGE_ASSESSMENT,
    ],
)
def test_non_admin_denied_privileged(role, perm):
    assert not is_allowed(Principal("i", "s", role), perm)


def test_reader_cannot_write_records():
    assert not is_allowed(Principal("i", "s", Role.READER), Permission.WRITE_RECORDS)


def test_admin_has_all_permissions():
    assert all(is_allowed(Principal("i", "s", Role.ADMIN), p) for p in Permission)
