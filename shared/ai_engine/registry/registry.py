"""Façade du registre de modèles isolé par entreprise."""

from pathlib import Path
from typing import Any

from shared.ai_engine.contracts import ArtifactSerializer, ModelArtifact, TenantContext
from shared.ai_engine.model_registry.repository import FileSystemModelRepository


class ModelRegistry:
    """Stocke et retrouve les modèles par entreprise, module, tâche et version."""

    def __init__(
        self,
        root: Path | str = "var/models",
        serializer: ArtifactSerializer | None = None,
    ) -> None:
        self._repository = FileSystemModelRepository(root)
        self._serializer = serializer

    def model_directory(
        self,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
        version: str,
    ) -> Path:
        return self._repository.artifact_directory(
            tenant,
            module_code,
            task_code,
            version,
        )

    def save(
        self,
        model: Any,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
        version: str,
        filename: str = "model.bin",
    ) -> Path:
        if self._serializer is None:
            raise RuntimeError("A model serializer must be injected before saving")
        directory = self.model_directory(tenant, module_code, task_code, version)
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / filename
        self._serializer.save(model, destination)
        return destination

    def activate(
        self,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
        version: str,
    ) -> None:
        directory = self.model_directory(tenant, module_code, task_code, version)
        if not directory.exists():
            raise FileNotFoundError(directory)
        pointer = directory.parent / "ACTIVE"
        pointer.write_text(version, encoding="utf-8")

    def resolve_active(
        self,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
    ) -> ModelArtifact:
        return self._repository.resolve_active(tenant, module_code, task_code)
