from fastapi import FastAPI

from shrag.api.routes import router
from shrag.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.app_version, debug=settings.debug)
    app.include_router(router, prefix="/v1")
    # Backward-compatible legacy routes kept during deprecation window.
    app.include_router(router)
    return app


app = create_app()
