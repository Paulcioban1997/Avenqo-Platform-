from shared.ai_engine.connectors.base import PlannedConnector
from shared.ai_engine.contracts import SourceKind


class CSVConnector(PlannedConnector):
    """Définit la frontière d'inspection et d'ingestion des fichiers CSV."""

    kind = SourceKind.CSV
