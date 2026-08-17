from shared.ai_engine.connectors.base import PlannedConnector
from shared.ai_engine.contracts import SourceKind


class ExcelConnector(PlannedConnector):
    """Définit la frontière d'inspection et d'ingestion des classeurs Excel."""

    kind = SourceKind.EXCEL
