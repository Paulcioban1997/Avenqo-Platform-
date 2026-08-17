from shared.ai_engine.connectors.base import PlannedConnector
from shared.ai_engine.contracts import SourceKind


class RESTAPIConnector(PlannedConnector):
    """Définit la frontière d'inspection et d'ingestion des API REST."""

    kind = SourceKind.REST_API


# Ceci cest pour le moment un connecteur REST API de base. Il peut être étendu pour inclure des fonctionnalités spécifiques à l'API, telles que l'authentification, la pagination, etc.