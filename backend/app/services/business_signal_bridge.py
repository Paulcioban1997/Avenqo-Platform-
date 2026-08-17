"""Pont entre les résultats bruts des capacités IA et les `BusinessSignal` génériques.

Vit dans `backend/` (glue applicative), pas dans `shared.ai_engine` : convertit
un résultat déjà produit par le runtime actif (Prediction Runtime, Model
Registry) en `BusinessSignal`, sans jamais introduire de règle métier —
uniquement un mappage mécanique capacité -> champs du signal. Aucune logique
de module ici non plus (générique, réutilisable par tous les modules).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence
from uuid import UUID

from shared.ai_engine.decision_intelligence.contracts import BusinessSignal, SignalDirection
from shared.ai_engine.nlp.sentiment import SentimentAggregate

# Phase 24 : variation relative minimale, sur une mesure de tendance métier
# continue (demande, prix...), pour la considérer comme une opportunité ou un
# risque plutôt qu'une simple stabilité — seuil unique et documenté, partagé
# par toutes les capacités de tendance (jamais un seuil différent par tâche).
_SIGNIFICANT_TREND_CHANGE_RATIO = 0.10


def signal_from_forecast(
    company_id: UUID,
    module_code: str,
    task_code: str,
    entity: str,
    forecast: Mapping[str, Any],
    previous_value: float | None,
    confidence: float = 0.7,
) -> BusinessSignal:
    """Construit un signal à partir de la sortie de `ForecastingPredictionExecutor`."""

    points = forecast.get("forecast", [])
    predicted_value = float(points[-1]["prediction"]) if points else 0.0
    direction = SignalDirection.STABLE
    if previous_value is not None and previous_value != 0:
        if predicted_value > previous_value:
            direction = SignalDirection.UP
        elif predicted_value < previous_value:
            direction = SignalDirection.DOWN

    return BusinessSignal(
        company_id=company_id,
        module_code=module_code,
        task_code=task_code,
        capability="forecasting",
        entity=entity,
        metric=task_code,
        value=predicted_value,
        previous_value=previous_value,
        direction=direction,
        confidence=confidence,
    )


def signal_from_anomaly(
    company_id: UUID,
    module_code: str,
    task_code: str,
    entity: str,
    anomaly_score: float,
    is_anomaly: bool,
) -> BusinessSignal:
    """Construit un signal à partir d'un score de décision IsolationForest."""

    return BusinessSignal(
        company_id=company_id,
        module_code=module_code,
        task_code=task_code,
        capability="anomaly_detection",
        entity=entity,
        metric="anomaly_score",
        value=float(anomaly_score),
        direction=SignalDirection.ANOMALY if is_anomaly else SignalDirection.STABLE,
        confidence=0.8 if is_anomaly else 0.5,
    )


def signal_from_classification(
    company_id: UUID,
    module_code: str,
    task_code: str,
    entity: str,
    probability: float,
) -> BusinessSignal:
    """Construit un signal à partir d'une probabilité de classification binaire."""

    return BusinessSignal(
        company_id=company_id,
        module_code=module_code,
        task_code=task_code,
        capability="classification",
        entity=entity,
        metric="risk_probability",
        value=float(probability),
        direction=SignalDirection.RISK if probability >= 0.5 else SignalDirection.STABLE,
        confidence=float(max(probability, 1 - probability)),
    )


def signal_from_segmentation(
    company_id: UUID,
    module_code: str,
    task_code: str,
    entity: str,
    segment_share: float,
) -> BusinessSignal:
    """Construit un signal à partir d'une part/mesure de segment (clustering)."""

    return BusinessSignal(
        company_id=company_id,
        module_code=module_code,
        task_code=task_code,
        capability="segmentation",
        entity=entity,
        metric="segment_share",
        value=float(segment_share),
        direction=SignalDirection.STABLE,
        confidence=0.6,
    )


def signal_from_regression(
    company_id: UUID,
    module_code: str,
    task_code: str,
    entity: str,
    value: float,
    previous_value: float | None,
    confidence: float = 0.6,
) -> BusinessSignal:
    """Construit un signal à partir d'une valeur numérique prédite (prix, demande...).

    Phase 25 : `capability` = fonction métier (`task_code`, ex. "demand"/"price"),
    jamais la famille d'algorithme ML — celle-ci reste en metadata interne.
    """

    direction = SignalDirection.STABLE
    if previous_value is not None and previous_value != 0:
        if value > previous_value:
            direction = SignalDirection.UP
        elif value < previous_value:
            direction = SignalDirection.DOWN

    return BusinessSignal(
        company_id=company_id,
        module_code=module_code,
        task_code=task_code,
        capability=task_code,
        entity=entity,
        metric=task_code,
        value=float(value),
        previous_value=previous_value,
        direction=direction,
        confidence=confidence,
        metadata={"ml_family": "regression"},
    )


def signal_from_business_trend(
    company_id: UUID,
    module_code: str,
    task_code: str,
    entity: str,
    metric: str,
    value: float,
    previous_value: float | None,
    confidence: float = 0.6,
) -> BusinessSignal:
    """Construit un signal de tendance métier continue (demande, prix...).

    Contrairement à `signal_from_regression` (UP/DOWN/STABLE, générique pour
    toute régression ponctuelle), cette fonction produit une direction
    OPPORTUNITY/RISK/STABLE fondée sur la variation relative par rapport à
    `previous_value`, comparée à un seuil unique et centralisé
    (`_SIGNIFICANT_TREND_CHANGE_RATIO`) — jamais un score technique ni un
    seuil différent par capacité (Phase 24, harmonisation).
    """

    direction = SignalDirection.STABLE
    if previous_value not in (None, 0):
        change_ratio = (value - previous_value) / abs(previous_value)
        if change_ratio >= _SIGNIFICANT_TREND_CHANGE_RATIO:
            direction = SignalDirection.OPPORTUNITY
        elif change_ratio <= -_SIGNIFICANT_TREND_CHANGE_RATIO:
            direction = SignalDirection.RISK

    return BusinessSignal(
        company_id=company_id,
        module_code=module_code,
        task_code=task_code,
        # Phase 25 : capability = fonction métier (task_code), jamais la
        # famille d'algorithme ML (conservée en metadata interne).
        capability=task_code,
        entity=entity,
        metric=metric,
        value=float(value),
        previous_value=previous_value,
        direction=direction,
        confidence=confidence,
        metadata={"ml_family": "regression"},
    )


def signal_from_recommendation(
    company_id: UUID,
    module_code: str,
    task_code: str,
    entity: str,
    recommended_items: Sequence[str],
    confidence: float = 0.5,
) -> BusinessSignal:
    """Construit un signal à partir d'une liste d'articles recommandés (Phase 22).

    Jamais un score technique : la "valeur" métier est simplement le nombre
    d'articles recommandés (une opportunité de vente croisée), utilisée par
    la Business Decision Layer sans jamais exposer d'algorithme.
    """

    return BusinessSignal(
        company_id=company_id,
        module_code=module_code,
        task_code=task_code,
        capability="recommendation",
        entity=entity,
        metric="recommended_items_count",
        value=float(len(recommended_items)),
        direction=SignalDirection.OPPORTUNITY if recommended_items else SignalDirection.STABLE,
        confidence=confidence,
        metadata={"recommended_items": tuple(recommended_items)},
    )


def signal_from_sentiment(
    company_id: UUID,
    module_code: str,
    task_code: str,
    entity: str,
    aggregate: SentimentAggregate,
) -> BusinessSignal:
    """Construit un signal à partir d'une agrégation de sentiment (Phase 23).

    Jamais un score de modèle brut : la "valeur" métier est le taux d'avis
    négatifs, avec la tendance (amélioration/dégradation) comme direction —
    le détail (pourcentages, thèmes les plus négatifs, insatisfactions fortes
    récentes) reste en métadonnée pour la couche de décision.
    """

    direction = SignalDirection.STABLE
    if aggregate.trend == "worsening":
        direction = SignalDirection.RISK
    elif aggregate.trend == "improving":
        direction = SignalDirection.OPPORTUNITY

    return BusinessSignal(
        company_id=company_id,
        module_code=module_code,
        task_code=task_code,
        capability="sentiment_analysis",
        entity=entity,
        metric="negative_sentiment_rate",
        value=float(aggregate.negative_rate),
        previous_value=aggregate.previous_negative_rate,
        direction=direction,
        confidence=0.6,
        metadata={
            "positive_rate": aggregate.positive_rate,
            "neutral_rate": aggregate.neutral_rate,
            "negative_count": aggregate.negative_count,
            "total_analyzed": aggregate.total_analyzed,
            "trend": aggregate.trend,
            "top_negative_entities": aggregate.top_negative_entities,
            "recent_strong_negative_count": aggregate.recent_strong_negative_count,
        },
    )


# Capacité IA -> fonction de conversion, utilisée par `signal_from_prediction`
# pour rester générique (aucun `if capability == ...` dupliqué ailleurs).
_SIGNAL_BUILDERS: dict[str, Any] = {
    "forecasting": lambda company_id, module_code, task_code, entity, outcome, previous_value: signal_from_forecast(
        company_id, module_code, task_code, entity, outcome["result"], previous_value,
        confidence=outcome.get("confidence") or 0.7,
    ),
    "classification": lambda company_id, module_code, task_code, entity, outcome, previous_value: signal_from_classification(
        company_id, module_code, task_code, entity, _positive_class_probability(outcome),
    ),
    "regression": lambda company_id, module_code, task_code, entity, outcome, previous_value: signal_from_regression(
        company_id, module_code, task_code, entity, outcome["result"], previous_value,
        confidence=outcome.get("confidence") or 0.6,
    ),
    "segmentation": lambda company_id, module_code, task_code, entity, outcome, previous_value: signal_from_segmentation(
        company_id, module_code, task_code, entity, outcome.get("confidence") or 0.5,
    ),
    "anomaly_detection": lambda company_id, module_code, task_code, entity, outcome, previous_value: signal_from_anomaly(
        company_id, module_code, task_code, entity,
        outcome.get("confidence") if outcome.get("confidence") is not None else (1.0 if _is_anomaly(outcome) else 0.0),
        _is_anomaly(outcome),
    ),
}


def _positive_class_probability(outcome: Mapping[str, Any]) -> float:
    """Reconstruit une probabilité de la classe positive depuis un résultat sklearn brut."""

    confidence = outcome.get("confidence") if outcome.get("confidence") is not None else 0.5
    result = outcome.get("result")
    is_positive = result in (1, 1.0, True, "1")
    return confidence if is_positive else 1 - confidence


def _is_anomaly(outcome: Mapping[str, Any]) -> bool:
    """IsolationForest renvoie -1 pour une anomalie, 1 pour un point normal."""

    return outcome.get("result") in (-1, -1.0, "anomaly")


def signal_from_prediction(
    company_id: UUID,
    module_code: str,
    task_code: str,
    capability: str,
    entity: str,
    outcome: Mapping[str, Any],
    previous_value: float | None = None,
) -> BusinessSignal:
    """Point d'entrée générique : convertit une sortie brute de prédiction en signal.

    Aiguillage par capacité (jamais par module ni par nom de modèle) : ajouter
    une nouvelle capacité se fait en ajoutant une entrée à `_SIGNAL_BUILDERS`.
    """

    builder = _SIGNAL_BUILDERS.get(capability)
    if builder is None:
        return signal_from_regression(company_id, module_code, task_code, entity, outcome["result"], previous_value)
    return builder(company_id, module_code, task_code, entity, outcome, previous_value)
