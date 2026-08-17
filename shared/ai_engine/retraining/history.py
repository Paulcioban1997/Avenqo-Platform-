"""Historique complet des ré-entraînements — persistance via le `ModelRegistry`
existant, sans le modifier (mêmes principes que `drift/serializer.py`).

L'historique est à l'échelle de la **tâche** (pas d'une version particulière) :
`ModelRegistry.model_directory(...)` n'expose qu'un dossier par version, donc
ce module réutilise ce même helper uniquement pour remonter à son dossier
parent (`.parent`), commun à toutes les versions et au pointeur `ACTIVE` —
zéro nouvelle méthode requise sur `ModelRegistry`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.registry.registry import ModelRegistry
from shared.ai_engine.retraining.types import RetrainingDecision

HISTORY_FILENAME = "retraining_history.joblib"

# Segment de version "factice" — jamais réellement écrit à cet emplacement,
# uniquement utilisé pour obtenir `.parent` via l'API existante de
# `ModelRegistry` (respecte `_SAFE_SEGMENT`, ne collisionne jamais avec un
# vrai numéro de version au format `%Y%m%d%H%M%S%f`, entièrement numérique).
_TASK_LEVEL_PLACEHOLDER_VERSION = "taskroot"


class RetrainingOutcome(StrEnum):
    """Résultat final d'une vérification/tentative de ré-entraînement."""

    NOT_NEEDED = "not_needed"
    ACTIVATED = "activated"
    KEPT_PREVIOUS = "kept_previous"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RetrainingHistoryEntry:
    """Une ligne d'historique — jamais exposée à l'utilisateur final."""

    decision: RetrainingDecision
    outcome: RetrainingOutcome
    triggered_rules: tuple[str, ...] = ()
    previous_version: str | None = None
    previous_model_name: str | None = None
    candidate_version: str | None = None
    candidate_model_name: str | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True, slots=True)
class RetrainingHistory:
    """Journal immuable, complet, des vérifications/tentatives de ré-entraînement."""

    entries: tuple[RetrainingHistoryEntry, ...] = ()

    def append(self, entry: RetrainingHistoryEntry) -> "RetrainingHistory":
        return RetrainingHistory(entries=self.entries + (entry,))


def _task_directory(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
) -> Path:
    return registry.model_directory(
        tenant, module_code, task_code, _TASK_LEVEL_PLACEHOLDER_VERSION
    ).parent


def load_history(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
) -> RetrainingHistory:
    """Recharge l'historique existant, ou un historique vide s'il n'existe pas encore."""

    import joblib

    path = _task_directory(registry, tenant, module_code, task_code) / HISTORY_FILENAME
    if not path.exists():
        return RetrainingHistory()
    return joblib.load(path)


def append_history_entry(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    entry: RetrainingHistoryEntry,
) -> RetrainingHistory:
    """Ajoute une entrée à l'historique existant et le persiste — jamais destructif."""

    import joblib

    history = load_history(registry, tenant, module_code, task_code).append(entry)
    directory = _task_directory(registry, tenant, module_code, task_code)
    directory.mkdir(parents=True, exist_ok=True)
    joblib.dump(history, directory / HISTORY_FILENAME)
    return history
