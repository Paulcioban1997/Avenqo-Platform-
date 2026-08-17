"""Point d'entrée unique de la couche Auto Retraining (interne, admin uniquement).

`evaluate_retraining` est appelée par le backend pour décider — seule, sans
intervention utilisateur — s'il faut ré-entraîner. `compare_models` implémente
la comparaison obligatoire avant toute activation : un candidat ne remplace
jamais un bon modèle par un moins bon. Les deux fonctions sont défensives
(never-raise), même principe que `drift.service.run_drift_check`.
"""

from __future__ import annotations

import logging
from typing import Mapping

from shared.ai_engine.drift.types import DriftSeverity
from shared.ai_engine.retraining.decision_engine import DecisionEngine
from shared.ai_engine.retraining.registry import primary_metric_for
from shared.ai_engine.retraining.types import (
    ModelComparisonResult,
    RetrainingDecision,
    RetrainingDecisionResult,
    RetrainingRulesConfig,
    RetrainingSignals,
)

logger = logging.getLogger(__name__)


def evaluate_retraining(
    signals: RetrainingSignals,
    config: RetrainingRulesConfig | None = None,
) -> RetrainingDecisionResult:
    """Évalue toutes les règles configurées — ne lève jamais.

    Best-effort : toute erreur interne est absorbée et journalisée, en
    retournant `NO_ACTION` plutôt que de risquer un ré-entraînement non
    maîtrisé ou de faire échouer l'appelant.
    """

    try:
        return DecisionEngine(config).evaluate(signals)
    except Exception:
        logger.warning("Échec de l'évaluation du ré-entraînement : NO_ACTION par défaut.", exc_info=True)
        return RetrainingDecisionResult(decision=RetrainingDecision.NO_ACTION)


def compare_models(
    family: str,
    previous_metrics: Mapping[str, float] | None,
    candidate_metrics: Mapping[str, float] | None,
    candidate_drift_severity: DriftSeverity | None = None,
    config: RetrainingRulesConfig | None = None,
) -> ModelComparisonResult:
    """Comparaison obligatoire ancien modèle vs. candidat — ne lève jamais.

    En cas d'erreur interne ou d'impossibilité de comparer (métrique
    manquante), la position la plus sûre est adoptée : conserver l'ancien
    modèle (`candidate_is_better=False`) plutôt que d'activer à l'aveugle.
    """

    config = config or RetrainingRulesConfig()
    try:
        metric_name, higher_is_better = primary_metric_for(family)
        previous_value = (previous_metrics or {}).get(metric_name)
        candidate_value = (candidate_metrics or {}).get(metric_name)
        if previous_value is None or candidate_value is None:
            return ModelComparisonResult(
                metric_name=metric_name,
                higher_is_better=higher_is_better,
                previous_value=previous_value,
                candidate_value=candidate_value,
                delta=None,
                candidate_is_better=False,
                blocked_by_drift=False,
            )

        delta = (
            candidate_value - previous_value
            if higher_is_better
            else previous_value - candidate_value
        )
        blocked_by_drift = bool(
            config.block_activation_on_critical_drift
            and candidate_drift_severity == DriftSeverity.CRITICAL
        )
        candidate_is_better = (delta >= -config.comparison_tolerance) and not blocked_by_drift
        return ModelComparisonResult(
            metric_name=metric_name,
            higher_is_better=higher_is_better,
            previous_value=previous_value,
            candidate_value=candidate_value,
            delta=delta,
            candidate_is_better=candidate_is_better,
            blocked_by_drift=blocked_by_drift,
        )
    except Exception:
        logger.warning(
            "Échec de la comparaison de modèles pour la famille '%s' : conservation de l'ancien modèle.",
            family,
            exc_info=True,
        )
        return ModelComparisonResult(
            metric_name=family,
            higher_is_better=True,
            previous_value=None,
            candidate_value=None,
            delta=None,
            candidate_is_better=False,
            blocked_by_drift=False,
        )


def should_activate(comparison: ModelComparisonResult) -> bool:
    """Seule source de vérité consultée avant d'activer un candidat."""

    return comparison.candidate_is_better
