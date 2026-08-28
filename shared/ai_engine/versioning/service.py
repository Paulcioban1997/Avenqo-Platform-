"""Point d'entrÃ©e unique de la couche Model Versioning (interne, admin uniquement).

`record_version` est appelÃ©e par `TrainingDispatcher` aprÃ¨s CHAQUE
entraÃ®nement/rÃ©entraÃ®nement â€” automatique, sans intervention utilisateur,
sans bouton. Elle ne recalcule jamais rien (mÃ©triques, drift, XAI) : elle ne
fait que capturer les rÃ©sultats dÃ©jÃ  produits ailleurs. Comme
`retraining/service.py`, elle ne lÃ¨ve jamais : un Ã©chec de traÃ§abilitÃ© ne
doit jamais faire Ã©chouer un entraÃ®nement.

`list_versions`/`get_version`/`compare`/`rollback` sont les opÃ©rations de
lecture/administration, utilisÃ©es par le backend (API interne uniquement,
jamais par le frontend Avenqo).
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import replace
from typing import Any, Mapping

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.drift.types import DriftReport
from shared.ai_engine.experiments import DatasetSnapshot, SearchMethod
from shared.ai_engine.registry.registry import ModelRegistry
from shared.ai_engine.retraining.types import RetrainingRulesConfig
from shared.ai_engine.versioning.comparison import compare_versions
from shared.ai_engine.versioning.lifecycle import reconcile_lifecycle_states
from shared.ai_engine.versioning.history import (
    VersionHistory,
    VersionHistoryEntry,
    append_version_history_entry,
    load_version_history,
)
from shared.ai_engine.versioning.registry import (
    active_version,
    list_versions as _list_version_strings,
    next_version_number,
)
from shared.ai_engine.versioning.rollback import rollback_to_version as _rollback_to_version
from shared.ai_engine.versioning.serializer import load_version_record, save_version_record
from shared.ai_engine.versioning.types import (
    ModelLifecycleState,
    RollbackResult,
    VersionComparisonResult,
    VersionEventType,
    VersionRecord,
    VersionSummary,
)

logger = logging.getLogger(__name__)


def invalidate_dataset_versions(
    registry: ModelRegistry,
    tenant: TenantContext,
    dataset_id: str,
) -> int:
    """Remove model artifacts derived from one tenant dataset and clear stale pointers."""

    tenant_directory = registry.model_directory(
        tenant, "tenantroot", "taskroot", "versionroot"
    ).parents[2]
    removed = 0
    if not tenant_directory.is_dir():
        return removed
    for module_directory in tenant_directory.iterdir():
        if not module_directory.is_dir():
            continue
        for task_directory in module_directory.iterdir():
            if not task_directory.is_dir():
                continue
            removed_versions: set[str] = set()
            for version_directory in task_directory.iterdir():
                if not version_directory.is_dir():
                    continue
                try:
                    record = load_version_record(
                        registry,
                        tenant,
                        module_directory.name,
                        task_directory.name,
                        version_directory.name,
                    )
                except (FileNotFoundError, OSError):
                    continue
                if record.dataset_id != dataset_id:
                    continue
                removed_versions.add(version_directory.name)
                shutil.rmtree(version_directory)
                removed += 1
            active_pointer = task_directory / "ACTIVE"
            if active_pointer.is_file():
                active = active_pointer.read_text(encoding="utf-8").strip()
                if active in removed_versions:
                    active_pointer.unlink()
    return removed


def record_version(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    version: str,
    family: str,
    model_type: str,
    model_name: str,
    dataset: DatasetSnapshot,
    hyperparameters: Mapping[str, Any],
    search_method: SearchMethod,
    metrics: Mapping[str, float],
    parent_version: str | None,
    activated: bool,
    baseline_metrics: Mapping[str, float] | None = None,
    quality_approved: bool | None = None,
    quality_reason: str | None = None,
    drift_report: DriftReport | None = None,
    has_explanation: bool = False,
    retraining_reason: str | None = None,
    triggered_rules: tuple[str, ...] = (),
) -> VersionRecord | None:
    """Capture et persiste une fiche de version complÃ¨te â€” ne lÃ¨ve jamais.

    Best-effort, comme `retraining.service.evaluate_retraining` : toute
    erreur interne est absorbÃ©e et journalisÃ©e plutÃ´t que de faire Ã©chouer
    l'entraÃ®nement qui vient pourtant de rÃ©ussir.
    """

    try:
        existing = _list_version_strings(registry, tenant, module_code, task_code)
        version_number = next_version_number(existing, version)
        next_state = ModelLifecycleState.PRODUCTION if activated else ModelLifecycleState.VALIDATED
        record = VersionRecord(
            version=version,
            version_number=version_number,
            parent_version=parent_version,
            module_code=module_code,
            task_code=task_code,
            family=family,
            model_type=model_type,
            model_name=model_name,
            dataset_id=str(dataset.dataset_id),
            dataset_row_count=dataset.row_count,
            dataset_fingerprint=dataset.fingerprint,
            dataset_uri=dataset.uri,
            hyperparameters=dict(hyperparameters),
            search_method=search_method,
            metrics=dict(metrics),
            baseline_metrics=(
                dict(baseline_metrics) if baseline_metrics is not None else None
            ),
            quality_approved=quality_approved,
            quality_reason=quality_reason,
            state=next_state,
            drift_severity=drift_report.overall_severity if drift_report is not None else None,
            has_drift_report=drift_report is not None,
            has_explanation=has_explanation,
            retraining_reason=retraining_reason,
            triggered_rules=triggered_rules,
        )
        save_version_record(registry, record, tenant)

        append_version_history_entry(
            registry,
            tenant,
            module_code,
            task_code,
            VersionHistoryEntry(
                event=VersionEventType.CREATED,
                version=version,
                version_number=version_number,
                parent_version=parent_version,
                triggered_by="manual" if triggered_rules and "manual" in triggered_rules else "system",
            ),
        )
        if activated:
            previous_active = active_version(registry, tenant, module_code, task_code)
            registry.activate(tenant, module_code, task_code, version)
            reconcile_lifecycle_states(
                registry,
                tenant,
                module_code,
                task_code,
                promoted_version=version,
                previous_active_version=previous_active,
            )
            append_version_history_entry(
                registry,
                tenant,
                module_code,
                task_code,
                VersionHistoryEntry(
                    event=VersionEventType.ACTIVATED,
                    version=version,
                    version_number=version_number,
                    parent_version=parent_version,
                ),
            )
        return record
    except Exception:
        logger.warning(
            "Ã‰chec de l'enregistrement de la version pour module=%s task=%s version=%s",
            module_code,
            task_code,
            version,
            exc_info=True,
        )
        return None


def get_version(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    version: str,
) -> VersionRecord:
    """Recharge la fiche complÃ¨te d'une version â€” lÃ¨ve `FileNotFoundError` si absente."""

    return load_version_record(registry, tenant, module_code, task_code, version)


def list_versions(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
) -> tuple[VersionSummary, ...]:
    """Liste toutes les versions (jamais supprimÃ©es) avec leur statut actif."""

    current_active = active_version(registry, tenant, module_code, task_code)
    summaries = []
    for version in _list_version_strings(registry, tenant, module_code, task_code):
        try:
            record = load_version_record(registry, tenant, module_code, task_code, version)
        except FileNotFoundError:
            continue
        summaries.append(
            VersionSummary(
                version=record.version,
                version_number=record.version_number,
                parent_version=record.parent_version,
                model_name=record.model_name,
                is_active=record.version == current_active,
                state=record.state,
                retraining_reason=record.retraining_reason,
                created_at=record.created_at,
            )
        )
    return tuple(summaries)


def get_history(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
) -> VersionHistory:
    """Journal complet du cycle de vie des versions (crÃ©ations, activations, rollbacks)."""

    return load_version_history(registry, tenant, module_code, task_code)


def compare(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    version_a: str,
    version_b: str,
    config: RetrainingRulesConfig | None = None,
) -> VersionComparisonResult:
    """Compare deux versions dÃ©jÃ  entraÃ®nÃ©es â€” aucun recalcul de mÃ©triques/drift/XAI."""

    record_a = load_version_record(registry, tenant, module_code, task_code, version_a)
    record_b = load_version_record(registry, tenant, module_code, task_code, version_b)
    return compare_versions(record_a, record_b, config)


def rollback(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    target_version: str,
) -> RollbackResult:
    """Restaure `target_version` comme version active â€” sans rÃ©entraÃ®nement."""

    return _rollback_to_version(registry, tenant, module_code, task_code, target_version)

