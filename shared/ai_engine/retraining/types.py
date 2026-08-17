"""Types partagés de la couche Auto Retraining (usage interne uniquement).

Comme `explainability/types.py` (Phase 6) et `drift/types.py` (Phase 7), ces
objets ne sont jamais exposés à l'utilisateur final : consommés uniquement
par le backend, les tâches internes/admin et les futures phases (Monitoring,
Alerting, AutoML).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum, StrEnum
from typing import Any, Mapping

from shared.ai_engine.drift.types import ConceptDriftReport, DriftSeverity


class RetrainingDecision(IntEnum):
    """Sévérité croissante — `IntEnum` pour permettre `max()` directement.

    Même principe que `DriftSeverity` (Phase 7) : plus la valeur est élevée,
    plus le signal de ré-entraînement est fort.
    """

    NO_ACTION = 0
    WAIT = 1
    RETRAIN_RECOMMENDED = 2
    RETRAIN_REQUIRED = 3
    RETRAIN_CRITICAL = 4


def max_decision(*decisions: RetrainingDecision) -> RetrainingDecision:
    """Agrège plusieurs décisions : la plus sévère l'emporte toujours."""

    return max(decisions) if decisions else RetrainingDecision.NO_ACTION


class RetrainingReason(StrEnum):
    """Catégorie de déclencheur ayant produit une décision (usage interne)."""

    DRIFT = "drift"
    DATA_VOLUME = "data_volume"
    MODEL_AGE = "model_age"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    SCHEDULED = "scheduled"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    """Résultat de l'évaluation d'une règle individuelle et configurable."""

    rule_name: str
    reason: RetrainingReason
    triggered: bool
    decision: RetrainingDecision
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrainingSignals:
    """Faits observés, rassemblés par l'appelant (backend), consommés par les règles.

    Volontairement dépourvu de tout accès disque/BD ici : ce module reste pur
    et testable en isolation — la collecte des faits (requêtes SQL, lecture du
    dernier `DriftReport`...) vit côté backend.
    """

    data_drift_severity: DriftSeverity = DriftSeverity.NONE
    concept_drift: ConceptDriftReport | None = None
    rows_at_last_training: int = 0
    rows_current: int = 0
    last_trained_at: datetime | None = None
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    scheduled_due: bool = False
    manual_trigger_requested: bool = False


@dataclass(frozen=True, slots=True)
class RetrainingRulesConfig:
    """Seuils et sévérités configurables — source unique des décisions.

    Chaque règle est indépendamment activable/désactivable et sa sévérité de
    sortie configurable, pour rester adaptable par entreprise/module sans
    jamais toucher à la logique de calcul (même principe que
    `drift/thresholds.py`).
    """

    enable_drift_rule: bool = True
    enable_data_volume_rule: bool = True
    enable_model_age_rule: bool = True
    enable_performance_rule: bool = True
    enable_scheduled_rule: bool = True
    enable_manual_rule: bool = True

    drift_warning_decision: RetrainingDecision = RetrainingDecision.WAIT
    drift_critical_decision: RetrainingDecision = RetrainingDecision.RETRAIN_CRITICAL

    min_new_rows: int = 5000
    data_volume_decision: RetrainingDecision = RetrainingDecision.RETRAIN_REQUIRED

    max_model_age_days: int = 30
    model_age_decision: RetrainingDecision = RetrainingDecision.RETRAIN_REQUIRED

    performance_warning_decision: RetrainingDecision = RetrainingDecision.RETRAIN_RECOMMENDED
    performance_critical_decision: RetrainingDecision = RetrainingDecision.RETRAIN_REQUIRED

    scheduled_interval_days: int = 7
    scheduled_decision: RetrainingDecision = RetrainingDecision.RETRAIN_REQUIRED

    manual_decision: RetrainingDecision = RetrainingDecision.RETRAIN_CRITICAL

    # Seuil à partir duquel une décision déclenche un ré-entraînement réel :
    # `WAIT`/`RETRAIN_RECOMMENDED` seuls restent de simples signaux d'alerte
    # (exploitables plus tard par la phase Monitoring/Alerting).
    action_threshold: RetrainingDecision = RetrainingDecision.RETRAIN_REQUIRED

    # Tolérance de comparaison (voir `service.compare_models`) : un candidat
    # à égalité (delta >= -tolérance) est considéré comme au moins aussi bon.
    comparison_tolerance: float = 0.0
    block_activation_on_critical_drift: bool = True


@dataclass(frozen=True, slots=True)
class RetrainingDecisionResult:
    """Décision agrégée + détail de chaque règle évaluée (audit interne)."""

    decision: RetrainingDecision
    outcomes: tuple[RuleOutcome, ...] = ()
    triggered_rules: tuple[RuleOutcome, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelComparisonResult:
    """Résultat de la comparaison obligatoire ancien modèle vs. candidat.

    Ne remplace jamais un bon modèle par un moins bon : `candidate_is_better`
    est la seule source de vérité consultée avant toute activation.
    """

    metric_name: str
    higher_is_better: bool
    previous_value: float | None
    candidate_value: float | None
    delta: float | None
    candidate_is_better: bool
    blocked_by_drift: bool = False
