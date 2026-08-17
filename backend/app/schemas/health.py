from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Décrit la réponse de la route de contrôle de santé."""

    status: str
    application: str
    version: str
    environment: str
