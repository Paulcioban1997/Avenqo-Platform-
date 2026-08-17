from shared.ai_engine.connectors.base import PlannedConnector
from shared.ai_engine.contracts import SourceKind


class SQLiteConnector(PlannedConnector):
    """Définit la frontière d'inspection et d'ingestion pour SQLite."""

    kind = SourceKind.SQLITE
