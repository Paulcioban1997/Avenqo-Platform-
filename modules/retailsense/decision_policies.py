"""Règles Business Decision Intelligence propres à RetailSenseAI.

Enregistrées dans les registres génériques
(`shared.ai_engine.decision_intelligence`) sans jamais introduire de
``if module == "retail"`` dans le cœur générique : ce fichier EST l'endroit
où vivent les règles spécifiques au retail (même principe que
`modules/retailsense/training_specs.py` pour la configuration ML).
"""

from __future__ import annotations

from typing import Sequence

from shared.ai_engine.decision_intelligence.action_rules import ActionRuleRegistry
from shared.ai_engine.decision_intelligence.contracts import (
    BusinessInsight,
    BusinessSignal,
    RecommendedAction,
    Severity,
    SignalDirection,
)
from shared.ai_engine.decision_intelligence.cross_capability import CrossCapabilityRuleRegistry

_STOCK_RISK_CAPABILITY = "cross_capability.stock_risk"
_CUSTOMER_RISK_CAPABILITY = "cross_capability.customer_risk"
_CHURN_SEGMENTATION_CAPABILITY = "cross_capability.churn_segmentation"


def _stock_risk_rule(signals: Sequence[BusinessSignal]) -> BusinessInsight | None:
    """Prévision de demande en hausse + anomalie détectée -> risque de rupture de stock."""

    forecast_signal = next(
        (s for s in signals if s.capability == "forecasting" and s.direction == SignalDirection.UP), None
    )
    anomaly_signal = next((s for s in signals if s.capability == "anomaly_detection"), None)
    if forecast_signal is None or anomaly_signal is None:
        return None
    return BusinessInsight(
        title="Risque de rupture de stock",
        summary=(
            "La demande devrait augmenter alors qu'un comportement inhabituel a été "
            f"détecté pour {anomaly_signal.entity}."
        ),
        capability=_STOCK_RISK_CAPABILITY,
        reasons=(
            f"prévision en hausse: {forecast_signal.value:.2f}",
            f"anomalie détectée: {anomaly_signal.entity}",
        ),
        severity=Severity.HIGH,
        confidence=min(forecast_signal.confidence, anomaly_signal.confidence),
        signals=(forecast_signal, anomaly_signal),
    )


def _customer_risk_rule(signals: Sequence[BusinessSignal]) -> BusinessInsight | None:
    """Segment de clients à forte valeur + risque de mauvaise expérience -> alerte fidélisation.

    Phase 23 (harmonisation) : exclut explicitement task_code == "churn", déjà
    couvert par la règle plus spécifique `_churn_segmentation_rule` ci-dessous.
    Sans cette exclusion, les deux règles se déclenchent simultanément sur les
    mêmes signaux (churn + segmentation) et produisent deux décisions quasi
    identiques sur la même population de clients — la règle la plus
    spécifique doit toujours prévaloir sur la règle générique pour la même
    population, jamais les deux à la fois.
    """

    segmentation_signal = next((s for s in signals if s.capability == "segmentation"), None)
    risk_signal = next(
        (
            s
            for s in signals
            if s.capability == "classification" and s.direction == SignalDirection.RISK and s.task_code != "churn"
        ),
        None,
    )
    if segmentation_signal is None or risk_signal is None:
        return None
    return BusinessInsight(
        title="Clients à forte valeur en risque d'insatisfaction",
        summary=(
            f"Des clients du segment « {segmentation_signal.entity} » présentent un "
            "risque d'insatisfaction élevé."
        ),
        capability=_CUSTOMER_RISK_CAPABILITY,
        reasons=(
            f"segment: {segmentation_signal.entity}",
            f"risque: {risk_signal.value:.0%}",
        ),
        severity=Severity.HIGH,
        confidence=min(segmentation_signal.confidence, risk_signal.confidence),
        signals=(segmentation_signal, risk_signal),
    )


def _stock_risk_action(insight: BusinessInsight) -> RecommendedAction:
    return RecommendedAction(
        type="REVIEW_INVENTORY",
        title="Vérifier les stocks et préparer un réapprovisionnement",
        description=insight.summary,
        expected_impact=insight.severity,
        urgency=insight.severity,
        requires_approval=True,
    )


def _customer_risk_action(insight: BusinessInsight) -> RecommendedAction:
    return RecommendedAction(
        type="CUSTOMER_RETENTION",
        title="Prioriser le suivi des clients à forte valeur",
        description=insight.summary,
        expected_impact=insight.severity,
        urgency=insight.severity,
        requires_approval=True,
    )


def _churn_segmentation_rule(signals: Sequence[BusinessSignal]) -> BusinessInsight | None:
    """Phase 22 : clients à risque de départ (churn) qui appartiennent au

    segment le plus fréquent parmi eux (proxy honnête de "forte valeur" en
    l'absence d'une colonne monétaire dédiée) -> décision de rétention
    ciblée, dans le format exact attendu par le métier."""

    churn_signal = next(
        (s for s in signals if s.task_code == "churn" and s.direction == SignalDirection.RISK), None
    )
    segmentation_signal = next((s for s in signals if s.capability == "segmentation"), None)
    if churn_signal is None or segmentation_signal is None:
        return None
    high_value_count = int(segmentation_signal.value)
    if high_value_count <= 0:
        return None
    return BusinessInsight(
        title=f"{high_value_count} clients à forte valeur présentent un risque élevé de départ.",
        summary="Valeur commerciale potentiellement à risque.",
        capability=_CHURN_SEGMENTATION_CAPABILITY,
        reasons=(
            f"clients à risque de départ: {int(churn_signal.value)}",
            f"dont à forte valeur: {high_value_count}",
        ),
        severity=Severity.HIGH,
        confidence=min(churn_signal.confidence, segmentation_signal.confidence),
        signals=(churn_signal, segmentation_signal),
    )


def _churn_segmentation_action(insight: BusinessInsight) -> RecommendedAction:
    return RecommendedAction(
        type="RETENTION_CAMPAIGN",
        title="Créer une campagne de rétention ciblée pour ces clients.",
        description=insight.summary,
        expected_impact=insight.severity,
        urgency=insight.severity,
        requires_approval=True,
    )


def register_retail_decision_policies(
    cross_capability_registry: CrossCapabilityRuleRegistry,
    action_registry: ActionRuleRegistry,
) -> None:
    """Enregistre les règles RetailSenseAI dans les registres génériques injectés."""

    cross_capability_registry.register(_stock_risk_rule)
    cross_capability_registry.register(_customer_risk_rule)
    cross_capability_registry.register(_churn_segmentation_rule)
    action_registry.register(_STOCK_RISK_CAPABILITY, _stock_risk_action)
    action_registry.register(_CUSTOMER_RISK_CAPABILITY, _customer_risk_action)
    action_registry.register(_CHURN_SEGMENTATION_CAPABILITY, _churn_segmentation_action)
