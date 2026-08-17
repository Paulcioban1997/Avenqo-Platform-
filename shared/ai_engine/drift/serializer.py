"""Persistance des artefacts de drift — via le `ModelRegistry` existant, sans le modifier.

Mêmes principes que `shared.ai_engine.explainability.serializer` : centralise
uniquement les noms de fichiers conventionnels (`drift_baseline.joblib`,
`drift_report.joblib`), en réutilisant `ModelRegistry.save()`/
`.model_directory()` tels quels — zéro changement du `ModelRegistry` requis.
"""

from __future__ import annotations

from pathlib import Path

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.drift.types import DriftReport, ReferenceBaseline
from shared.ai_engine.registry.registry import ModelRegistry

BASELINE_FILENAME = "drift_baseline.joblib"
DRIFT_REPORT_FILENAME = "drift_report.joblib"


def save_baseline(
    registry: ModelRegistry,
    baseline: ReferenceBaseline,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    version: str,
) -> Path:
    """Enregistre la baseline de référence à côté du modèle versionné."""

    return registry.save(baseline, tenant, module_code, task_code, version, filename=BASELINE_FILENAME)


def load_baseline(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    version: str,
) -> ReferenceBaseline:
    """Recharge la baseline de référence précédemment enregistrée pour cette version."""

    import joblib

    directory = registry.model_directory(tenant, module_code, task_code, version)
    path = directory / BASELINE_FILENAME
    if not path.exists():
        raise FileNotFoundError(path)
    return joblib.load(path)


def save_drift_report(
    registry: ModelRegistry,
    report: DriftReport,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    version: str,
) -> Path:
    """Enregistre le rapport de drift, associé à la version qui l'a détecté."""

    return registry.save(report, tenant, module_code, task_code, version, filename=DRIFT_REPORT_FILENAME)


def load_drift_report(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    version: str,
) -> DriftReport:
    """Recharge le rapport de drift précédemment enregistré pour cette version."""

    import joblib

    directory = registry.model_directory(tenant, module_code, task_code, version)
    path = directory / DRIFT_REPORT_FILENAME
    if not path.exists():
        raise FileNotFoundError(path)
    return joblib.load(path)
