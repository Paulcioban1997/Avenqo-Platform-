"""Moteur de rollback — change uniquement la version active, jamais de réentraînement.

Réutilise `ModelRegistry.activate()` (déjà existant, jamais modifié) : un
rollback n'est qu'un appel à `activate()` vers une version PASSÉE plutôt que
vers une version fraîchement entraînée. Aucune version n'est jamais
supprimée : le pointeur `ACTIVE` change, tous les répertoires de version
restent intacts et disponibles (archivage total, comme demandé).
"""

from __future__ import annotations

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.exceptions import ModelNotFoundError
from shared.ai_engine.registry.registry import ModelRegistry
from shared.ai_engine.versioning.history import VersionHistoryEntry, append_version_history_entry
from shared.ai_engine.versioning.lifecycle import reconcile_lifecycle_states
from shared.ai_engine.versioning.registry import active_version, list_versions
from shared.ai_engine.versioning.serializer import load_version_record
from shared.ai_engine.versioning.types import RollbackResult, VersionEventType


def rollback_to_version(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    target_version: str,
) -> RollbackResult:
    """Restaure `target_version` comme version active — sans réentraînement.

    Lève `ModelNotFoundError` si `target_version` n'existe pas pour cette
    tâche : un rollback vers une version inexistante est une erreur
    d'utilisation (jamais un cas silencieux), à l'inverse des fonctions
    "never-raise" de la couche Auto Retraining (Phase 8) qui ne doivent
    jamais interrompre un entraînement automatique.
    """

    existing = list_versions(registry, tenant, module_code, task_code)
    if target_version not in existing:
        raise ModelNotFoundError(
            f"Version '{target_version}' introuvable pour module '{module_code}', "
            f"tâche '{task_code}'"
        )

    previous_active = active_version(registry, tenant, module_code, task_code)
    registry.activate(tenant, module_code, task_code, target_version)
    reconcile_lifecycle_states(
        registry,
        tenant,
        module_code,
        task_code,
        promoted_version=target_version,
        previous_active_version=previous_active,
    )

    target_record = load_version_record(registry, tenant, module_code, task_code, target_version)
    append_version_history_entry(
        registry,
        tenant,
        module_code,
        task_code,
        VersionHistoryEntry(
            event=VersionEventType.ROLLED_BACK,
            version=target_version,
            version_number=target_record.version_number,
            parent_version=previous_active,
            triggered_by="manual_rollback",
            detail={"previous_active_version": previous_active} if previous_active else {},
        ),
    )

    return RollbackResult(
        module_code=module_code,
        task_code=task_code,
        previous_active_version=previous_active,
        target_version=target_version,
        activated=True,
    )
