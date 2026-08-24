from pydantic import BaseModel


class ReadinessResponse(BaseModel):
    """Décrit la réponse du contrôle de disponibilité (dépendances critiques).

    Ne révèle jamais de secrets, de mots de passe de connexion ou de chemins
    de système de fichiers — uniquement des booléens/états sûrs.
    """

    status: str
    database: str
    ai_providers: dict[str, str]
    stripe_configured: bool
