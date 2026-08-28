"""Types partagés de la couche Model Versioning (usage interne uniquement).

Comme `explainability/types.py` (Phase 6), `drift/types.py` (Phase 7) et
`retraining/types.py` (Phase 8), ces objets ne sont jamais exposés à
l'utilisateur final : consommés uniquement par le backend et les API
internes/admin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping

from shared.ai_engine.drift.types import DriftSeverity
from shared.ai_engine.experiments import SearchMethod


class ModelLifecycleState(StrEnum):
    """État interne de cycle de vie d'une version — jamais exposé au frontend."""

    TRAINING = "training"
    VALIDATED = "validated"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"
    ROLLED_BACK = "rolled_back"


class VersionEventType(StrEnum):
    """Catégorie d'événement du cycle de vie d'une version (audit complet)."""

    CREATED = "created"
    ACTIVATED = "activated"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True, slots=True)
class VersionRecord:
    """Fiche complète d'une version de modèle — jamais recalculée, jamais supprimée.

    Persistée une seule fois à la création de la version, à côté du modèle,
    de l'explication et du rapport de drift (même répertoire versionné que
    `ModelRegistry` gère déjà). `version` reste l'identifiant technique
    existant (le nom du répertoire, déjà utilisé par `ModelRegistry`,
    `drift/serializer.py`, `explainability/serializer.py` et
    `retraining/history.py`) : aucune deuxième source de vérité pour
    "où vit cette version" n'est introduite ici.
    """

    version: str
    version_number: int
    parent_version: str | None
    module_code: str
    task_code: str
    family: str
    model_type: str
    model_name: str
    dataset_id: str
    dataset_row_count: int
    dataset_fingerprint: str
    dataset_uri: str
    hyperparameters: Mapping[str, Any]
    search_method: SearchMethod
    metrics: Mapping[str, float]
    baseline_metrics: Mapping[str, float] | None = None
    quality_approved: bool | None = None
    quality_reason: str | None = None
    state: ModelLifecycleState = ModelLifecycleState.TRAINING
    drift_severity: DriftSeverity | None = None
    has_drift_report: bool = False
    has_explanation: bool = False
    retraining_reason: str | None = None
    triggered_rules: tuple[str, ...] = ()
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True, slots=True)
class VersionSummary:
    """Vue légère d'une version — utilisée pour lister sans ambiguïté sur l'état actif."""

    version: str
    version_number: int
    parent_version: str | None
    model_name: str
    is_active: bool
    state: ModelLifecycleState
    retraining_reason: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class VersionComparisonResult:
    """Compare deux versions déjà entraînées — jamais de recalcul de métriques/drift/XAI.

    Délègue entièrement à `retraining.service.compare_models` (source unique
    de vérité pour "qu'est-ce qu'un modèle meilleur qu'un autre") : ce type
    ajoute uniquement l'identification des deux versions comparées.
    """

    version_a: str
    version_b: str
    metric_name: str
    higher_is_better: bool
    value_a: float | None
    value_b: float | None
    delta: float | None
    b_is_better: bool
    blocked_by_drift: bool


@dataclass(frozen=True, slots=True)
class RollbackResult:
    """Résultat d'un rollback — jamais de réentraînement, seul le pointeur ACTIVE change."""

    module_code: str
    task_code: str
    previous_active_version: str | None
    target_version: str
    activated: bool
