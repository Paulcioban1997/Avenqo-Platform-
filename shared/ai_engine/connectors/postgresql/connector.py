from shared.ai_engine.connectors.base import PlannedConnector
from shared.ai_engine.contracts import SourceKind


class PostgreSQLConnector(PlannedConnector):
    """Définit la frontière d'inspection et d'ingestion pour PostgreSQL."""

    kind = SourceKind.POSTGRESQL
