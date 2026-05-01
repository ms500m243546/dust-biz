"""API entry point - FastAPI app factory and router wiring."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app as app_pkg
from app.api import API_PREFIX, API_VERSION
from app.api.routes import health, meta
from app.config.settings import get_settings

__all__ = ["API_PREFIX", "API_VERSION", "app", "create_app"]


def create_app() -> FastAPI:
    settings = get_settings()
    fastapi_app = FastAPI(
        title="DustOps AI",
        version=app_pkg.__version__,
        description=(
            "Production-preserving dust-risk optimization platform for mines. "
            "See docs/system-map.md for subsystem boundaries."
        ),
    )

    if settings.cors_allow_origins:
        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_allow_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    fastapi_app.include_router(health.router, prefix=API_PREFIX, tags=["meta"])
    fastapi_app.include_router(meta.router, prefix=API_PREFIX, tags=["meta"])

    return fastapi_app


app = create_app()
