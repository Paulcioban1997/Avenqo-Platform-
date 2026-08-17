from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import api_router
from backend.app.config.settings import get_settings
from backend.app.core.exception_handlers import register_exception_handlers
from backend.app.core.logging import configure_logging
from backend.app.database import create_database_tables
from backend.app.middlewares.request_id import RequestIDMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Prépare les ressources persistantes de l'application."""

    create_database_tables()
    yield  # yield = "pause" the context manager, allowing the app to run


def create_application() -> FastAPI:
    """Crée et configure l'instance de l'application FastAPI."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_title,
        description=settings.app_description,
        version=settings.app_version,
        lifespan=lifespan,
        swagger_ui_parameters={"persistAuthorization": True},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/", tags=["root"])
    async def root() -> dict[str, str]:
        return {
            "application": "PMC Solutions AI Platform",
            "status": "online",
            "version": "0.1.0",
            "documentation": "/docs",
        }

    return app


app = create_application()
