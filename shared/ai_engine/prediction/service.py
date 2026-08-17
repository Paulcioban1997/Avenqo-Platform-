from typing import Any, Mapping, Protocol

from shared.ai_engine.contracts import ModelArtifact, TenantContext
from shared.ai_engine.model_registry.repository import FileSystemModelRepository


class PredictionExecutor(Protocol):
    def predict(self, artifact: ModelArtifact, features: Mapping[str, Any]) -> Any: ...


class PredictionService:
    """Retrouve uniquement le modèle actif appartenant à l'entreprise courante."""

    def __init__(self, model_repository: FileSystemModelRepository) -> None:
        self._models = model_repository

    def predict(
        self,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
        features: Mapping[str, Any],
        executor: PredictionExecutor,
    ) -> Any:
        artifact = self._models.resolve_active(tenant, module_code, task_code)
        return executor.predict(artifact, features)
