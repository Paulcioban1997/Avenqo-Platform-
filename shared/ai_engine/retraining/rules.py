"""Règles de ré-entraînement — chacune indépendamment configurable/activable.

Fonctions pures (aucun accès disque/BD/réseau) : chaque règle prend les
`RetrainingSignals` déjà rassemblés par l'appelant (backend) et la
configuration active, puis retourne un `RuleOutcome` — ou `None` si la règle
est désactivée. `decision_engine.py` les combine ensuite en une décision
unique (la plus sévère l'emporte).
"""

from __future__ import annotations

from datetime import timedelta

from shared.ai_engine.drift.types import DriftSeverity
from shared.ai_engine.retraining.types import (
    RetrainingDecision,
    RetrainingReason,
    RetrainingRulesConfig,
    RetrainingSignals,
    RuleOutcome,
)


def evaluate_drift_rule(
    signals: RetrainingSignals, config: RetrainingRulesConfig
) -> RuleOutcome | None:
    """Drift critique détecté sur les données/prédictions/cible (hors concept drift,
    couvert séparément par `evaluate_performance_rule` pour rester indépendamment
    configurable)."""

    if not config.enable_drift_rule:
        return None

    severity = signals.data_drift_severity
    detail = {"severity": severity.name}
    if severity == DriftSeverity.CRITICAL:
        return RuleOutcome("drift", RetrainingReason.DRIFT, True, config.drift_critical_decision, detail)
    if severity == DriftSeverity.WARNING:
        return RuleOutcome("drift", RetrainingReason.DRIFT, True, config.drift_warning_decision, detail)
    return RuleOutcome("drift", RetrainingReason.DRIFT, False, RetrainingDecision.NO_ACTION, detail)


def evaluate_data_volume_rule(
    signals: RetrainingSignals, config: RetrainingRulesConfig
) -> RuleOutcome | None:
    """Volume important de nouvelles données depuis le dernier entraînement."""

    if not config.enable_data_volume_rule:
        return None

    new_rows = max(signals.rows_current - signals.rows_at_last_training, 0)
    detail = {"new_rows": new_rows, "threshold": config.min_new_rows}
    triggered = new_rows >= config.min_new_rows
    decision = config.data_volume_decision if triggered else RetrainingDecision.NO_ACTION
    return RuleOutcome("data_volume", RetrainingReason.DATA_VOLUME, triggered, decision, detail)


def evaluate_model_age_rule(
    signals: RetrainingSignals, config: RetrainingRulesConfig
) -> RuleOutcome | None:
    """Modèle actif trop ancien (aucun ré-entraînement depuis longtemps)."""

    if not config.enable_model_age_rule:
        return None

    if signals.last_trained_at is None:
        # Aucun modèle actif connu : rien à qualifier de "trop ancien" ici —
        # le premier entraînement n'est pas piloté par cette couche.
        return RuleOutcome(
            "model_age", RetrainingReason.MODEL_AGE, False, RetrainingDecision.NO_ACTION, {"age_days": None}
        )

    age_days = (signals.now - signals.last_trained_at) / timedelta(days=1)
    detail = {"age_days": age_days, "threshold_days": config.max_model_age_days}
    triggered = age_days >= config.max_model_age_days
    decision = config.model_age_decision if triggered else RetrainingDecision.NO_ACTION
    return RuleOutcome("model_age", RetrainingReason.MODEL_AGE, triggered, decision, detail)


def evaluate_performance_rule(
    signals: RetrainingSignals, config: RetrainingRulesConfig
) -> RuleOutcome | None:
    """Dégradation de la performance réelle (concept drift), déjà classifiée
    par la Phase 7 (`drift.thresholds.classify_metric_degradation`) — jamais
    recalculée ici, seulement réutilisée."""

    if not config.enable_performance_rule:
        return None

    concept = signals.concept_drift
    if concept is None or not concept.available:
        return RuleOutcome(
            "performance_degradation",
            RetrainingReason.PERFORMANCE_DEGRADATION,
            False,
            RetrainingDecision.NO_ACTION,
            {"available": False},
        )

    detail = {
        "metric_name": concept.metric_name,
        "degradation_ratio": concept.degradation_ratio,
    }
    if concept.severity == DriftSeverity.CRITICAL:
        return RuleOutcome(
            "performance_degradation",
            RetrainingReason.PERFORMANCE_DEGRADATION,
            True,
            config.performance_critical_decision,
            detail,
        )
    if concept.severity == DriftSeverity.WARNING:
        return RuleOutcome(
            "performance_degradation",
            RetrainingReason.PERFORMANCE_DEGRADATION,
            True,
            config.performance_warning_decision,
            detail,
        )
    return RuleOutcome(
        "performance_degradation",
        RetrainingReason.PERFORMANCE_DEGRADATION,
        False,
        RetrainingDecision.NO_ACTION,
        detail,
    )


def evaluate_scheduled_rule(
    signals: RetrainingSignals, config: RetrainingRulesConfig
) -> RuleOutcome | None:
    """Ré-entraînement planifié (calendaire), indépendant de l'âge du modèle."""

    if not config.enable_scheduled_rule:
        return None

    detail = {"scheduled_due": signals.scheduled_due}
    decision = config.scheduled_decision if signals.scheduled_due else RetrainingDecision.NO_ACTION
    return RuleOutcome("scheduled", RetrainingReason.SCHEDULED, signals.scheduled_due, decision, detail)


def evaluate_manual_rule(
    signals: RetrainingSignals, config: RetrainingRulesConfig
) -> RuleOutcome | None:
    """Déclenchement manuel via l'API interne (jamais exposée à l'utilisateur final)."""

    if not config.enable_manual_rule:
        return None

    detail = {"manual_trigger_requested": signals.manual_trigger_requested}
    decision = config.manual_decision if signals.manual_trigger_requested else RetrainingDecision.NO_ACTION
    return RuleOutcome(
        "manual", RetrainingReason.MANUAL, signals.manual_trigger_requested, decision, detail
    )


# Registre des règles combinées par `decision_engine.DecisionEngine` — ajouter
# une règle plus tard ne nécessite qu'une nouvelle fonction + une entrée ici.
ALL_RULES = (
    evaluate_drift_rule,
    evaluate_data_volume_rule,
    evaluate_model_age_rule,
    evaluate_performance_rule,
    evaluate_scheduled_rule,
    evaluate_manual_rule,
)
