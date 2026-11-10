from datetime import datetime
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import __version__, roles, scope
from .authz import Permission, Principal, Role, require
from .config import Settings, get_settings
from .db import get_engine, get_session
from .economics_api import router as economics_router
from .tenancy import role_can_bypass_rls
from .usage import query as usage_query
from .usage import series as usage_series

_READ_USAGE = Depends(require(Permission.READ_USAGE))
_MANAGE_IDENTITY = Depends(require(Permission.MANAGE_IDENTITY))


class GrantBody(BaseModel):
    issuer: str = Field(min_length=1, max_length=512)
    subject: str = Field(min_length=1, max_length=512)
    provider: str = Field(min_length=1, max_length=32)
    account: str = Field(min_length=1, max_length=256)


class RoleBody(BaseModel):
    issuer: str = Field(min_length=1, max_length=512)
    subject: str = Field(min_length=1, max_length=512)
    role: Role


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _issuer(app: FastAPI) -> str | None:
    """Issuer for the CSP connect-src. A bad config must never break a response."""
    try:
        getter = app.dependency_overrides.get(get_settings, get_settings)
        return getter().oidc_issuer
    except Exception:
        return None


def create_app() -> FastAPI:
    app = FastAPI(title="CFA Tokenomics API", version=__version__, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        issuer = _issuer(app)
        connect = "'self'" + (f" {_origin(issuer)}" if issuer else "")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            f"img-src 'self' data:; connect-src {connect}; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.get("/config.json")
    def public_config(settings: Settings = Depends(get_settings)) -> dict[str, str | None]:
        """Public browser settings only. Never secrets."""
        return {
            "oidc_issuer": settings.oidc_issuer,
            "oidc_client_id": settings.oidc_client_id,
            "oidc_audience": settings.oidc_audience,
        }

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness only; reveals no configuration or customer data."""
        return {"status": "ok", "version": __version__}

    @app.get("/readyz")
    def readyz(response: Response, settings: Settings = Depends(get_settings)) -> dict[str, str]:
        engine = get_engine(settings)
        if engine is None:
            if settings.environment == "production":
                response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
                return {"status": "not_ready", "database": "not_configured"}
            return {"status": "ready", "database": "not_configured"}
        try:
            with engine.connect() as conn:
                conn.execute(text("select 1"))
                bypass = role_can_bypass_rls(conn)
        except Exception:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not_ready", "database": "unreachable"}
        if bypass and not settings.allow_rls_bypass:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not_ready", "database": "role_bypasses_rls"}
        return {"status": "ready", "database": "ok"}

    @app.get("/v1/whoami")
    def whoami(principal: Principal = _READ_USAGE) -> dict[str, str]:
        """Authentication check: the caller's mapped role. No data access."""
        return {"role": principal.role.value}

    @app.get("/v1/usage")
    def get_usage(
        start: datetime,
        end: datetime,
        provider: str | None = None,
        account: str | None = None,
        model_id: str | None = None,
        sku: str | None = None,
        source_type: str | None = None,
        principal: Principal = _READ_USAGE,
        db: Session = Depends(get_session),
    ) -> dict:
        """Reconciled usage for a bounded range, limited to the caller's account scope."""
        try:
            allowed = scope.allowed_accounts(db, principal)
            return usage_query.usage(
                db, start, end, provider, account, model_id, allowed, sku, source_type
            )
        except usage_query.QueryError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None

    @app.get("/v1/usage/series")
    def get_series(
        start: datetime,
        end: datetime,
        category: str,
        bucket: str = "hour",
        group_by: Annotated[list[str] | None, Query()] = None,
        provider: str | None = None,
        account: str | None = None,
        model_id: str | None = None,
        sku: str | None = None,
        source_type: str | None = None,
        principal: Principal = _READ_USAGE,
        db: Session = Depends(get_session),
    ) -> dict:
        """Bucketed series for one token category, limited to the caller's account scope."""
        try:
            allowed = scope.allowed_accounts(db, principal)
            return usage_series.series(
                db, start, end, category, bucket, tuple(group_by or ["provider"]),
                provider, account, model_id, sku, source_type, allowed,
            )  # fmt: skip
        except usage_series.SeriesError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None

    @app.put("/v1/admin/roles", status_code=status.HTTP_204_NO_CONTENT)
    def put_role(
        body: RoleBody,
        actor: Principal = _MANAGE_IDENTITY,
        db: Session = Depends(get_session),
        settings: Settings = Depends(get_settings),
    ) -> None:
        try:
            roles.assign_role(db, settings, actor, body.issuer, body.subject, body.role)
        except roles.RoleError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

    @app.delete("/v1/admin/roles", status_code=status.HTTP_204_NO_CONTENT)
    def delete_role(
        issuer: str,
        subject: str,
        actor: Principal = _MANAGE_IDENTITY,
        db: Session = Depends(get_session),
        settings: Settings = Depends(get_settings),
    ) -> None:
        try:
            roles.remove_role(db, settings, actor, issuer, subject)
        except roles.RoleError as exc:
            code = 404 if "no such" in str(exc) else status.HTTP_409_CONFLICT
            raise HTTPException(code, str(exc)) from None

    @app.put("/v1/admin/grants", status_code=status.HTTP_204_NO_CONTENT)
    def put_grant(
        body: GrantBody,
        actor: Principal = _MANAGE_IDENTITY,
        db: Session = Depends(get_session),
    ) -> None:
        scope.grant(db, actor, **body.model_dump())

    @app.delete("/v1/admin/grants", status_code=status.HTTP_204_NO_CONTENT)
    def delete_grant(
        issuer: str,
        subject: str,
        provider: str,
        account: str,
        actor: Principal = _MANAGE_IDENTITY,
        db: Session = Depends(get_session),
    ) -> None:
        if not scope.revoke(db, actor, issuer, subject, provider, account):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no such grant")

    app.include_router(economics_router)

    web_dir = get_settings().web_dir if _web_enabled() else None
    if web_dir and Path(web_dir).is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


def _web_enabled() -> bool:
    try:
        return get_settings().web_dir is not None
    except Exception:  # invalid production config is reported at startup elsewhere
        return False


app = create_app()
