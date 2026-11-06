from fastapi import Depends, FastAPI

from . import __version__
from .authz import Permission, Principal, require
from .config import Settings, get_settings

_READ_USAGE = Depends(require(Permission.READ_USAGE))


def create_app() -> FastAPI:
    app = FastAPI(title="CFA Tokenomics API", version=__version__, docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        """Liveness only; reveals no configuration or customer data."""
        return {"status": "ok", "version": __version__}

    @app.get("/readyz")
    def readyz(settings: Settings = Depends(get_settings)) -> dict[str, str]:
        # Real dependency checks (database, secret store, identity) arrive with their adapters.
        return {"status": "ready", "environment": settings.environment}

    @app.get("/v1/usage")
    def usage(_: Principal = _READ_USAGE) -> dict[str, list]:
        """Placeholder permission-gated route. No usage ledger exists yet."""
        return {"observations": []}

    return app


app = create_app()
