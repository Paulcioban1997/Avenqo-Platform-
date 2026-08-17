"""Scoring métier déterministe et explicable (severity/business_impact/urgency/priority).

Aucun second modèle ML : formule simple, pondérée, à seuils explicites et
testable. Amplitude relative du signal, pondérée par la confiance du modèle
source et, si disponible, par la tendance historique du contexte métier.
"""

from __future__ import annotations

from shared.ai_engine.decision_intelligence.contracts import (
    BusinessSignal,
    DecisionContext,
    Severity,
    SignalDirection,
)

_SEVERITY_ORDER = (
    Severity.INFORMATIONAL,
    Severity.LOW,
    Severity.MEDIUM,
    Severity.HIGH,
    Severity.CRITICAL,
)


def _magnitude(signal: BusinessSignal) -> float:
    """Amplitude relative du signal (0..1), indépendante de l'unité métier."""

    if signal.direction in (SignalDirection.ANOMALY, SignalDirection.RISK):
        # value est déjà un score/une probabilité normalisée (0..1).
        return max(0.0, min(1.0, signal.value))
    if signal.previous_value in (None, 0):
        return 0.5  # pas de référence : amplitude neutre, ni négligée ni exagérée
    change = abs(signal.value - signal.previous_value) / abs(signal.previous_value)
    return max(0.0, min(1.0, change))


def _severity_from_score(score: float) -> Severity:
    if score >= 0.75:
        return Severity.CRITICAL
    if score >= 0.55:
        return Severity.HIGH
    if score >= 0.35:
        return Severity.MEDIUM
    if score >= 0.15:
        return Severity.LOW
    return Severity.INFORMATIONAL


def compute_severity(signal: BusinessSignal) -> Severity:
    """severity = amplitude du signal, pondérée par sa confiance."""

    score = _magnitude(signal) * max(0.1, signal.confidence)
    return _severity_from_score(score)


def compute_business_impact(signal: BusinessSignal, context: DecisionContext) -> Severity:
    """business_impact = amplitude, amplifiée si la tendance historique confirme le signal."""

    score = _magnitude(signal)
    trend = context.historical_trend.get(signal.metric)
    if trend is not None and signal.direction in (SignalDirection.UP, SignalDirection.RISK) and trend > 0:
        score = min(1.0, score + 0.15)
    return _severity_from_score(score * max(0.1, signal.confidence))


def compute_urgency(signal: BusinessSignal, context: DecisionContext) -> Severity:
    """urgency = amplitude seule (agir vite reste utile même si la confiance est faible)."""

    score = _magnitude(signal)
    if signal.direction in (SignalDirection.ANOMALY, SignalDirection.RISK):
        score = min(1.0, score + 0.1)
    return _severity_from_score(score)


def compute_priority(
    severity: Severity, business_impact: Severity, urgency: Severity, confidence: float
) -> Severity:
    """priority = pire des trois dimensions, plafonnée si la confiance est trop faible."""

    worst_index = max(_SEVERITY_ORDER.index(dimension) for dimension in (severity, business_impact, urgency))
    if confidence < 0.4:
        worst_index = min(worst_index, _SEVERITY_ORDER.index(Severity.MEDIUM))
    return _SEVERITY_ORDER[worst_index]
