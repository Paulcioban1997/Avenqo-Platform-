from shared.ai_engine.connectors.registry import ConnectorRegistry
from shared.ai_engine.contracts import DataSource, DetectedSchema


class SchemaDetectionService:
    """Délègue aux connecteurs la découverte des tables, colonnes et anomalies."""

    def __init__(self, connectors: ConnectorRegistry) -> None:
        self._connectors = connectors

    def detect(self, source: DataSource) -> DetectedSchema:
        return self._connectors.get(source.kind).inspect(source)
