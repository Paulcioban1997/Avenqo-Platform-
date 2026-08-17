from shared.ai_engine.connectors.base import PlannedConnector
from shared.ai_engine.contracts import SourceKind


class SQLServerConnector(PlannedConnector):
    """Définit la frontière d'inspection et d'ingestion pour SQL Server."""

    kind = SourceKind.SQLSERVER
