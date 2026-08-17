from shared.ai_engine.connectors.base import PlannedConnector
from shared.ai_engine.contracts import SourceKind


class MySQLConnector(PlannedConnector):
    """Définit la frontière d'inspection et d'ingestion pour MySQL."""

    kind = SourceKind.MYSQL
