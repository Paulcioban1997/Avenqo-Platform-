from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.app.api.router import api_router
from backend.app.config.settings import get_settings
from backend.app.core.exception_handlers import register_exception_handlers
from backend.app.core.logging import configure_logging
from backend.app.database import create_database_tables
from backend.app.middlewares.request_id import RequestIDMiddleware
from backend.app.middlewares.security_headers import SecurityHeadersMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Prépare les ressources persistantes de l'application."""

    settings = get_settings()
    is_production = settings.environment.lower() in {"production", "prod"}
    if not is_production:
        # Dev/test uniquement : filet de sécurité pratique. En production, le
        # schéma doit être géré exclusivement par `alembic upgrade head`
        # exécuté comme étape de déploiement explicite — voir
        # docs/production-deployment.md § Migrations.
        create_database_tables()
    yield  # yield = "pause" the context manager, allowing the app to run


def create_application() -> FastAPI:
    """Crée et configure l'instance de l'application FastAPI."""
    settings = get_settings()
    configure_logging(settings.log_level)
    is_production = settings.environment.lower() in {"production", "prod"}

    app = FastAPI(
        title=settings.app_title,
        description=settings.app_description,
        version=settings.app_version,
        lifespan=lifespan,
        swagger_ui_parameters={"persistAuthorization": True},
        # En production, aucun endpoint de debug/documentation interactif n'est exposé
        # publiquement (voir docs/production-deployment.md § Production config).
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Stripe-Signature"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(SecurityHeadersMiddleware, force_https=is_production)
    app.add_middleware(RequestIDMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/", tags=["root"])
    async def root() -> dict[str, str]:
        return {
            "application": settings.app_name,
            "status": "online",
            "version": settings.app_version,
            "documentation": "/docs" if not is_production else "unavailable",
        }

    return app


app = create_application()

