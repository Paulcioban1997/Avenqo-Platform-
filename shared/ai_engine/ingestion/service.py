from shared.ai_engine.connectors.registry import ConnectorRegistry
from shared.ai_engine.contracts import DataSource, TenantContext


class IngestionService:
    """Dirige l'ingestion vers le connecteur correspondant à la source."""

    def __init__(self, connectors: ConnectorRegistry) -> None:
        self._connectors = connectors

    def ingest(self, tenant: TenantContext, source: DataSource) -> str:
        return self._connectors.get(source.kind).ingest(tenant, source)
