from fastapi import Depends, FastAPI, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import __version__, roles
from .authz import Permission, Principal, Role, require
from .config import Settings, get_settings
from .db import get_engine, get_session

_READ_USAGE = Depends(require(Permission.READ_USAGE))
_MANAGE_IDENTITY = Depends(require(Permission.MANAGE_IDENTITY))


class RoleBody(BaseModel):
    issuer: str = Field(min_length=1, max_length=512)
    subject: str = Field(min_length=1, max_length=512)
    role: Role


def create_app() -> FastAPI:
    app = FastAPI(title="CFA Tokenomics API", version=__version__, docs_url=None, redoc_url=None)

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
        except Exception:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not_ready", "database": "unreachable"}
        return {"status": "ready", "database": "ok"}

    @app.get("/v1/usage")
    def usage(_: Principal = _READ_USAGE) -> dict[str, list]:
        """Placeholder permission-gated route. No usage ledger exists yet."""
        return {"observations": []}

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

    return app


app = create_app()
