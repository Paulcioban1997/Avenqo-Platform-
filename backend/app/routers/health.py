from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.ai.llm.health import ProviderHealthRegistry, get_provider_health_registry
from backend.app.config.settings import Settings, get_settings
from backend.app.database import get_db
from backend.app.schemas.health import HealthResponse
from backend.app.schemas.readiness import ReadinessResponse
from backend.app.services.artifact_storage_health import artifact_storage_health

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Renvoie l'état du service, sans toucher DB/fournisseurs IA/Stripe."""
    return HealthResponse(
        status="healthy",
        application=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get("/ready", response_model=ReadinessResponse)
def ready(
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
    health_registry: ProviderHealthRegistry = Depends(get_provider_health_registry),
) -> ReadinessResponse:
    """Vérifie les dépendances indispensables (DB, migrations, stockage)."""
    try:
        db.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception:
        database_status = "unavailable"

    storage_status = artifact_storage_health.check(Path(settings.artifact_root))

    migrations_status = "ok"
    if database_status == "ok":
        try:
            from alembic.config import Config
            from alembic.migration import MigrationContext
            from alembic.script import ScriptDirectory

            alembic_cfg = Config("alembic.ini")
            script = ScriptDirectory.from_config(alembic_cfg)
            head_rev = script.get_current_head()
            context = MigrationContext.configure(db.connection())
            current_rev = context.get_current_revision()
            if current_rev != head_rev:
                migrations_status = "pending"
        except Exception:
            migrations_status = "unverified"
    else:
        migrations_status = "unavailable"

    is_ready = (
        database_status == "ok"
        and storage_status.status == "ok"
        and migrations_status in {"ok", "unverified"}
    )

    return ReadinessResponse(
        status="ready" if is_ready else "degraded",
        database=database_status,
        artifact_storage=storage_status.status,
        ai_providers=dict(health_registry.snapshot()),
        stripe_configured=bool(settings.stripe_secret_key and settings.stripe_webhook_secret),
        migrations=migrations_status,
    )

