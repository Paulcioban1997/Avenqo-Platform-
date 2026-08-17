"""Historique du cycle de vie des versions — persistance via le `ModelRegistry`
existant, sans le modifier (même principe que `retraining/history.py`).

Distinct de `RetrainingHistory` (Phase 8) : celui-ci journalise pourquoi un
ré-entraînement a eu lieu, celui-ci journalise ce qui est arrivé à CHAQUE
version (créée, activée, ou restaurée par rollback) — y compris les
créations qui ne proviennent pas d'un ré-entraînement (premier entraînement).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.registry.registry import ModelRegistry
from shared.ai_engine.versioning.registry import task_directory
from shared.ai_engine.versioning.types import VersionEventType

VERSION_HISTORY_FILENAME = "version_history.joblib"


@dataclass(frozen=True, slots=True)
class VersionHistoryEntry:
    """Une ligne d'historique — jamais exposée à l'utilisateur final."""

    event: VersionEventType
    version: str
    version_number: int
    parent_version: str | None = None
    triggered_by: str = "system"
    detail: Mapping[str, Any] = field(default_factory=dict)
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True, slots=True)
class VersionHistory:
    """Journal immuable et complet du cycle de vie des versions d'une tâche."""

    entries: tuple[VersionHistoryEntry, ...] = ()

    def append(self, entry: VersionHistoryEntry) -> "VersionHistory":
        return VersionHistory(entries=self.entries + (entry,))


def load_version_history(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
) -> VersionHistory:
    """Recharge l'historique existant, ou un historique vide s'il n'existe pas encore."""

    import joblib

    path = task_directory(registry, tenant, module_code, task_code) / VERSION_HISTORY_FILENAME
    if not path.exists():
        return VersionHistory()
    return joblib.load(path)


def append_version_history_entry(
    registry: ModelRegistry,
    tenant: TenantContext,
    module_code: str,
    task_code: str,
    entry: VersionHistoryEntry,
) -> VersionHistory:
    """Ajoute une entrée à l'historique existant et le persiste — jamais destructif."""

    import joblib

    history = load_version_history(registry, tenant, module_code, task_code).append(entry)
    directory = task_directory(registry, tenant, module_code, task_code)
    directory.mkdir(parents=True, exist_ok=True)
    joblib.dump(history, directory / VERSION_HISTORY_FILENAME)
    return history
