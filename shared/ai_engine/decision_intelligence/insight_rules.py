"""Transforme un `BusinessSignal` en `BusinessInsight` — générique, par capacité.

Les règles sont enregistrées par CAPACITÉ IA générique (forecasting,
anomaly_detection, classification, segmentation), jamais par module ni par
task_code métier précis — c'est ce qui permet à RetailSenseAI, CRM AI,
Accounting AI, Marketing AI... de réutiliser exactement la même couche.
"""

from __future__ import annotations

from typing import Callable

from shared.ai_engine.decision_intelligence.contracts import (
    BusinessInsight,
    BusinessSignal,
    SignalDirection,
)
from shared.ai_engine.decision_intelligence.scoring import compute_severity

InsightRule = Callable[[BusinessSignal], BusinessInsight]


class InsightRuleRegistry:
    """Registre capacité -> règle. Vide -> repli générique sûr (jamais d'erreur)."""

    def __init__(self) -> None:
        self._rules: dict[str, InsightRule] = {}

    def register(self, capability: str, rule: InsightRule) -> None:
        self._rules[capability] = rule

    def build(self, signal: BusinessSignal) -> BusinessInsight:
        rule = self._rules.get(signal.capability, _generic_insight_rule)
        return rule(signal)


def _generic_insight_rule(signal: BusinessSignal) -> BusinessInsight:
    severity = compute_severity(signal)
    return BusinessInsight(
        title=f"Changement détecté sur {signal.metric}",
        summary=(
            f"La mesure « {signal.metric} » pour {signal.entity} affiche une valeur "
            f"de {signal.value:.2f}."
        ),
        capability=signal.capability,
        reasons=(f"valeur observée: {signal.value:.2f}", f"confiance: {signal.confidence:.0%}"),
        severity=severity,
        confidence=signal.confidence,
        signals=(signal,),
    )


def _forecasting_insight_rule(signal: BusinessSignal) -> BusinessInsight:
    severity = compute_severity(signal)
    change_percent = _percent_change(signal)
    trend_word = "augmenter" if signal.direction == SignalDirection.UP else "diminuer"
    change_text = f" d'environ {abs(change_percent):.0f} %" if change_percent is not None else ""
    reasons = tuple(
        reason
        for reason in (
            f"prévision: {signal.value:.2f}",
            f"valeur précédente: {signal.previous_value:.2f}" if signal.previous_value is not None else None,
            f"confiance: {signal.confidence:.0%}",
        )
        if reason is not None
    )
    return BusinessInsight(
        title=f"Évolution prévue de {signal.metric}",
        summary=(
            f"La mesure « {signal.metric} » pour {signal.entity} devrait {trend_word}"
            f"{change_text} dans la période à venir."
        ),
        capability=signal.capability,
        reasons=reasons,
        severity=severity,
        confidence=signal.confidence,
        signals=(signal,),
    )


def _anomaly_insight_rule(signal: BusinessSignal) -> BusinessInsight:
    severity = compute_severity(signal)
    return BusinessInsight(
        title="Comportement inhabituel détecté",
        summary=f"Une anomalie a été détectée pour {signal.entity} sur la mesure « {signal.metric} ».",
        capability=signal.capability,
        reasons=(f"score d'anomalie: {signal.value:.2f}", f"confiance: {signal.confidence:.0%}"),
        severity=severity,
        confidence=signal.confidence,
        signals=(signal,),
    )


def _segmentation_insight_rule(signal: BusinessSignal) -> BusinessInsight:
    """Phase 24 : message business-friendly dédié pour la part de portefeuille

    (`metric == "segment_share"`, voir `build_segmentation_signal`) ; conserve
    le message générique pour les autres mesures de segmentation déjà en
    place (ex. `high_value_at_risk_count`, combiné churn+segmentation).
    """

    severity = compute_severity(signal)
    if signal.metric == "segment_share":
        share_percent = signal.value * 100
        return BusinessInsight(
            title="Un segment client représente une part importante du portefeuille.",
            summary=(
                f"Le segment « {signal.entity} » représente environ {share_percent:.0f} % "
                "de vos clients."
            ),
            capability=signal.capability,
            reasons=(f"part du portefeuille: {share_percent:.0f} %",),
            severity=severity,
            confidence=signal.confidence,
            signals=(signal,),
        )
    return BusinessInsight(
        title=f"Segment « {signal.entity} » identifié",
        summary=(
            f"Le segment « {signal.entity} » représente une mesure de {signal.value:.2f} "
            f"sur « {signal.metric} »."
        ),
        capability=signal.capability,
        reasons=(f"mesure du segment: {signal.value:.2f}",),
        severity=severity,
        confidence=signal.confidence,
        signals=(signal,),
    )


def _classification_insight_rule(signal: BusinessSignal) -> BusinessInsight:
    severity = compute_severity(signal)
    return BusinessInsight(
        title=f"Risque détecté sur {signal.entity}",
        summary=f"Un risque élevé a été identifié pour {signal.entity} ({signal.metric}: {signal.value:.0%}).",
        capability=signal.capability,
        reasons=(f"probabilité: {signal.value:.0%}", f"confiance: {signal.confidence:.0%}"),
        severity=severity,
        confidence=signal.confidence,
        signals=(signal,),
    )


def _sentiment_insight_rule(signal: BusinessSignal) -> BusinessInsight:
    """Phase 23 : sentiment client, jamais de jargon NLP (pas "negative_class"/"logits")."""

    severity = compute_severity(signal)
    negative_count = int(signal.metadata.get("negative_count", 0))
    total_analyzed = int(signal.metadata.get("total_analyzed", 0))
    trend = signal.metadata.get("trend", "stable")

    if signal.direction == SignalDirection.RISK:
        title = "Le sentiment client s'est détérioré cette semaine."
        summary = "Une hausse des avis négatifs a été détectée."
    elif signal.direction == SignalDirection.OPPORTUNITY:
        title = "Le sentiment client s'améliore."
        summary = "La part d'avis négatifs a diminué récemment."
    else:
        title = "Sentiment client stable"
        summary = f"{negative_count} client(s) sur {total_analyzed} expriment une insatisfaction."

    return BusinessInsight(
        title=title,
        summary=summary,
        capability=signal.capability,
        reasons=(
            f"avis négatifs: {negative_count} sur {total_analyzed}",
            f"tendance: {trend}",
        ),
        severity=severity,
        confidence=signal.confidence,
        signals=(signal,),
    )


def _percent_change(signal: BusinessSignal) -> float | None:
    if signal.previous_value in (None, 0):
        return None
    return ((signal.value - signal.previous_value) / abs(signal.previous_value)) * 100


_REGRESSION_TASK_LABELS: dict[str, str] = {"demand": "la demande", "price": "le prix"}


def _regression_insight_rule(signal: BusinessSignal) -> BusinessInsight:
    """Phase 24/25 : demande/prix, jamais de jargon ML.

    Une seule règle pour ces deux capacités métier ("demand"/"price", comme
    `_classification_insight_rule` pour bad_review/churn) — le message varie
    par `task_code`, jamais par nom de modèle/algorithme.
    """

    severity = compute_severity(signal)
    label = _REGRESSION_TASK_LABELS.get(signal.task_code, f"« {signal.metric} »")

    if signal.direction == SignalDirection.OPPORTUNITY:
        if signal.task_code == "demand":
            title = "La demande devrait augmenter sensiblement."
        elif signal.task_code == "price":
            title = "Une opportunité d'ajustement de prix a été détectée."
        else:
            title = f"Une opportunité a été détectée sur {label}."
        summary = f"Une évolution favorable de {label} a été observée pour {signal.entity}."
    elif signal.direction == SignalDirection.RISK:
        if signal.task_code == "demand":
            title = "Une baisse de demande est anticipée."
        elif signal.task_code == "price":
            title = "Le prix observé s'écarte sensiblement de la tendance attendue."
        else:
            title = f"Un risque a été détecté sur {label}."
        summary = f"Une évolution défavorable de {label} a été observée pour {signal.entity}."
    else:
        if signal.task_code == "demand":
            title = "La demande demeure relativement stable."
        elif signal.task_code == "price":
            title = "Aucun changement significatif de prix n'est actuellement détecté."
        else:
            title = f"{label.capitalize()} demeure stable."
        summary = f"Aucun changement notable de {label} n'a été détecté pour {signal.entity}."

    reasons = tuple(
        reason
        for reason in (
            f"valeur observée: {signal.value:.2f}",
            f"valeur de référence: {signal.previous_value:.2f}" if signal.previous_value is not None else None,
            f"confiance: {signal.confidence:.0%}",
        )
        if reason is not None
    )
    return BusinessInsight(
        title=title,
        summary=summary,
        capability=signal.capability,
        reasons=reasons,
        severity=severity,
        confidence=signal.confidence,
        signals=(signal,),
    )


def _recommendation_insight_rule(signal: BusinessSignal) -> BusinessInsight:
    """Phase 24 : opportunités de vente croisée issues des recommandations."""

    severity = compute_severity(signal)
    opportunity_count = int(signal.value)
    if signal.direction == SignalDirection.OPPORTUNITY:
        title = "Des opportunités de ventes additionnelles ont été identifiées."
        summary = (
            f"{opportunity_count} client(s) présentent une opportunité de vente croisée "
            f"pour {signal.entity}."
        )
    else:
        title = "Aucune opportunité de vente croisée significative n'est actuellement détectée."
        summary = f"Aucune recommandation exploitable n'a été identifiée pour {signal.entity}."
    return BusinessInsight(
        title=title,
        summary=summary,
        capability=signal.capability,
        reasons=(f"opportunités identifiées: {opportunity_count}", f"confiance: {signal.confidence:.0%}"),
        severity=severity,
        confidence=signal.confidence,
        signals=(signal,),
    )


def build_default_insight_registry() -> InsightRuleRegistry:
    """Règles génériques couvrant les capacités déjà exécutables du runtime actif."""

    registry = InsightRuleRegistry()
    registry.register("forecasting", _forecasting_insight_rule)
    registry.register("anomaly_detection", _anomaly_insight_rule)
    registry.register("segmentation", _segmentation_insight_rule)
    registry.register("classification", _classification_insight_rule)
    registry.register("sentiment_analysis", _sentiment_insight_rule)
    # Phase 25 : capability = fonction métier ("demand"/"price"), plus "regression".
    registry.register("demand", _regression_insight_rule)
    registry.register("price", _regression_insight_rule)
    registry.register("recommendation", _recommendation_insight_rule)
    return registry
