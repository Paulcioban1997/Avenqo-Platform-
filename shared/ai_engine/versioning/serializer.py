"""Persistance du `VersionRecord` — via le `ModelRegistry` existant, sans le modifier.

Même principe que `drift/serializer.py` et `explainability/serializer.py` :
centralise uniquement le nom de fichier conventionnel, en réutilisant
`ModelRegistry.save()`/`.model_directory()` tels quels.
"""

from __future__ import annotations

from pathlib import Path

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.registry.registry import ModelRegistry
from shared.ai_engine.versioning.types import VersionRecord

VERSION_RECORD_FILENAME = "version_record.joblib"


def save_version_record(
    registry: ModelRegistry,
    record: VersionRecord,
    tenant: TenantContext,
) -> Path:
    """Enregistre la fiche de version, à côté du modèle versionné."""

    return registry.save(
        record,
        tenant,
        record.module_code,
        record.task_code,
        record.version,
        filename=VERSION_RECORD_FILENAME,
    )


def load_version_record(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    version: str,
) -> VersionRecord:
    """Recharge la fiche précédemment enregistrée pour cette version."""

    import joblib

    directory = registry.model_directory(tenant, module_code, task_code, version)
    path = directory / VERSION_RECORD_FILENAME
    if not path.exists():
        raise FileNotFoundError(path)
    return joblib.load(path)
