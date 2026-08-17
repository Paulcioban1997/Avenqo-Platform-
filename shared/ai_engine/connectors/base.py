"""Implémentation commune aux connecteurs de sources prévus."""

from shared.ai_engine.contracts import DataSource, DetectedSchema, SourceKind, TenantContext


class PlannedConnector:
    """Emplacement temporaire avant l'implémentation de l'adaptateur source."""

    kind: SourceKind

    def inspect(self, source: DataSource) -> DetectedSchema:
        raise NotImplementedError(f"{self.kind.value} schema inspection is not implemented")

    def ingest(self, tenant: TenantContext, source: DataSource) -> str:
        raise NotImplementedError(f"{self.kind.value} ingestion is not implemented")
