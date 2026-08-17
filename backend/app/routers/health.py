from fastapi import APIRouter

from backend.app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Renvoie l'état du service pour les contrôles de disponibilité."""
    return HealthResponse(
        status="healthy",
        application="PMC Solutions AI Platform",
        version="0.1.0",
        environment="development",
    )
