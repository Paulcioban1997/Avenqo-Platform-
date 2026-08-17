"""Dépôt d'artefacts de modèles isolé par entreprise."""

from __future__ import annotations

import re
from pathlib import Path

from shared.ai_engine.contracts import ModelArtifact, TenantContext
from shared.ai_engine.exceptions import ModelNotFoundError

_SAFE_SEGMENT = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class FileSystemModelRepository:
    """Retrouve les artefacts dans un espace immuable propre à l'entreprise."""

    def __init__(self, root: Path | str = "var/models") -> None:
        self._root = Path(root)

    def artifact_directory(
        self,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
        version: str,
    ) -> Path:
        self._validate_segments(module_code, task_code, version)
        return self._root / str(tenant.company_id) / module_code / task_code / version

    def resolve_active(
        self,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
    ) -> ModelArtifact:
        self._validate_segments(module_code, task_code)
        task_root = self._root / str(tenant.company_id) / module_code / task_code
        active_pointer = task_root / "ACTIVE"
        if not active_pointer.is_file():
            raise ModelNotFoundError(
                f"No active model exists for company '{tenant.company_id}', "
                f"module '{module_code}', task '{task_code}'"
            )
        version = active_pointer.read_text(encoding="utf-8").strip()
        artifact_path = self.artifact_directory(
            tenant,
            module_code,
            task_code,
            version,
        )
        return ModelArtifact(
            tenant=tenant,
            module_code=module_code,
            task_code=task_code,
            version=version,
            path=artifact_path,
            metrics={},
        )

    @staticmethod
    def _validate_segments(*segments: str) -> None:
        if any(not _SAFE_SEGMENT.fullmatch(segment) for segment in segments):
            raise ValueError("Artifact path segments must be normalized identifiers")
