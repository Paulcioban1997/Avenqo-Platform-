from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.ai.llm.health import ProviderHealthRegistry, get_provider_health_registry
from backend.app.config.settings import Settings, get_settings
from backend.app.database import get_db
from backend.app.schemas.health import HealthResponse
from backend.app.schemas.readiness import ReadinessResponse

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
    """Vérifie les dépendances indispensables (DB) sans appel coûteux aux
    fournisseurs IA/Stripe (juste leur état interne déjà connu / présence de
    configuration)."""
    try:
        db.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception:
        database_status = "unavailable"
    return ReadinessResponse(
        status="ready" if database_status == "ok" else "degraded",
        database=database_status,
        ai_providers=dict(health_registry.snapshot()),
        stripe_configured=bool(settings.stripe_secret_key and settings.stripe_webhook_secret),
    )

