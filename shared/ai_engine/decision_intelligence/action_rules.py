"""Génère une `RecommendedAction` à partir d'un `BusinessInsight` — par capacité.

Même principe que `insight_rules.py` : enregistré par capacité IA générique
(jamais par module), avec un repli générique sûr. `requires_approval=True`
systématiquement dans cette phase (aucune exécution automatique).
"""

from __future__ import annotations

from typing import Callable

from shared.ai_engine.decision_intelligence.contracts import BusinessInsight, RecommendedAction, SignalDirection

ActionRule = Callable[[BusinessInsight], RecommendedAction]


class ActionRuleRegistry:
    """Registre capacité -> règle. Vide -> repli générique sûr (jamais d'erreur)."""

    def __init__(self) -> None:
        self._rules: dict[str, ActionRule] = {}

    def register(self, capability: str, rule: ActionRule) -> None:
        self._rules[capability] = rule

    def build(self, insight: BusinessInsight) -> RecommendedAction:
        rule = self._rules.get(insight.capability, _generic_action_rule)
        return rule(insight)


def _generic_action_rule(insight: BusinessInsight) -> RecommendedAction:
    return RecommendedAction(
        type="REVIEW_INSIGHT",
        title="Examiner cette information",
        description=insight.summary,
        expected_impact=insight.severity,
        urgency=insight.severity,
        requires_approval=True,
    )


def _forecasting_action_rule(insight: BusinessInsight) -> RecommendedAction:
    return RecommendedAction(
        type="PREPARE_CAPACITY",
        title="Anticiper le changement de demande",
        description=insight.summary,
        expected_impact=insight.severity,
        urgency=insight.severity,
        requires_approval=True,
    )


def _anomaly_action_rule(insight: BusinessInsight) -> RecommendedAction:
    return RecommendedAction(
        type="INVESTIGATE_ANOMALY",
        title="Vérifier l'anomalie détectée",
        description=insight.summary,
        expected_impact=insight.severity,
        urgency=insight.severity,
        requires_approval=True,
    )


def _classification_action_rule(insight: BusinessInsight) -> RecommendedAction:
    return RecommendedAction(
        type="CUSTOMER_RETENTION",
        title="Prioriser un suivi client",
        description=insight.summary,
        expected_impact=insight.severity,
        urgency=insight.severity,
        requires_approval=True,
    )


def _sentiment_action_rule(insight: BusinessInsight) -> RecommendedAction:
    return RecommendedAction(
        type="REVIEW_NEGATIVE_FEEDBACK",
        title="Examiner les principaux motifs d'insatisfaction.",
        description=insight.summary,
        expected_impact=insight.severity,
        urgency=insight.severity,
        requires_approval=True,
    )


def _segmentation_action_rule(insight: BusinessInsight) -> RecommendedAction:
    return RecommendedAction(
        type="CUSTOMER_SEGMENT_CAMPAIGN",
        title="Examiner une campagne ciblée pour ce segment de clients.",
        description=insight.summary,
        expected_impact=insight.severity,
        urgency=insight.severity,
        requires_approval=True,
    )


def _regression_action_rule(insight: BusinessInsight) -> RecommendedAction:
    """Phase 24/25 : demande/prix, jamais d'automatisation.

    Une seule règle pour ces deux capacités métier (le message varie par
    `task_code` du signal d'origine, jamais par modèle/algorithme) — aucun
    ajustement de prix/stock n'est jamais appliqué automatiquement.
    """

    signal = insight.signals[0] if insight.signals else None
    task_code = signal.task_code if signal is not None else None
    direction = signal.direction if signal is not None else None

    if task_code == "demand":
        if direction == SignalDirection.OPPORTUNITY:
            return RecommendedAction(
                type="PREPARE_STOCK_CAPACITY",
                title="Anticiper les besoins de stock et ajuster les campagnes marketing.",
                description=insight.summary,
                expected_impact=insight.severity,
                urgency=insight.severity,
                requires_approval=True,
            )
        if direction == SignalDirection.RISK:
            return RecommendedAction(
                type="REVIEW_DEMAND_DECLINE",
                title="Examiner la baisse prévue et réduire le risque de surstock.",
                description=insight.summary,
                expected_impact=insight.severity,
                urgency=insight.severity,
                requires_approval=True,
            )
        return RecommendedAction(
            type="MONITOR_DEMAND",
            title="Surveiller l'évolution, aucune action urgente.",
            description=insight.summary,
            expected_impact=insight.severity,
            urgency=insight.severity,
            requires_approval=True,
        )

    if task_code == "price":
        if direction == SignalDirection.OPPORTUNITY:
            return RecommendedAction(
                type="REVIEW_PRICING_OPPORTUNITY",
                title="Examiner les produits concernés pour un ajustement de prix.",
                description=insight.summary,
                expected_impact=insight.severity,
                urgency=insight.severity,
                requires_approval=True,
            )
        if direction == SignalDirection.RISK:
            return RecommendedAction(
                type="REVIEW_PRICING_PRESSURE",
                title="Vérifier marge, concurrence et demande avant tout ajustement.",
                description=insight.summary,
                expected_impact=insight.severity,
                urgency=insight.severity,
                requires_approval=True,
            )
        return RecommendedAction(
            type="MAINTAIN_PRICING_STRATEGY",
            title="Conserver la stratégie de prix actuelle.",
            description=insight.summary,
            expected_impact=insight.severity,
            urgency=insight.severity,
            requires_approval=True,
        )

    return _generic_action_rule(insight)


def _recommendation_action_rule(insight: BusinessInsight) -> RecommendedAction:
    return RecommendedAction(
        type="PREPARE_CROSS_SELL_CAMPAIGN",
        title="Préparer une campagne de vente croisée personnalisée.",
        description=insight.summary,
        expected_impact=insight.severity,
        urgency=insight.severity,
        requires_approval=True,
    )


def build_default_action_registry() -> ActionRuleRegistry:
    """Règles génériques couvrant les capacités déjà exécutables du runtime actif."""

    registry = ActionRuleRegistry()
    registry.register("forecasting", _forecasting_action_rule)
    registry.register("anomaly_detection", _anomaly_action_rule)
    registry.register("classification", _classification_action_rule)
    registry.register("sentiment_analysis", _sentiment_action_rule)
    registry.register("segmentation", _segmentation_action_rule)
    # Phase 25 : capability = fonction métier ("demand"/"price"), plus "regression".
    registry.register("demand", _regression_action_rule)
    registry.register("price", _regression_action_rule)
    registry.register("recommendation", _recommendation_action_rule)
    return registry
