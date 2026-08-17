"""Contrats internes du Business Decision Intelligence Layer.

Générique et réutilisable par TOUT module Avenqo (RetailSenseAI, CRM AI,
Accounting AI, Marketing AI...) : aucune règle spécifique à un module ne vit
ici — uniquement les structures de données. Les règles métier concrètes sont
enregistrées par chaque module (voir `modules/retailsense/decision_policies.py`).

Chaîne de transformation : `BusinessSignal` (sortie brute d'une capacité IA)
-> `BusinessInsight` (fait métier, sans jargon ML) -> `BusinessDecision`
(priorisée, avec provenance) -> `RecommendedAction` (jamais exécutée
automatiquement, `requires_approval=True`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping
from uuid import UUID


class Severity(StrEnum):
    """Échelle unique réutilisée pour severity/business_impact/urgency/priority."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class SignalDirection(StrEnum):
    """Sens du changement détecté — jamais un terme ML (pas "class_1"/"anomaly_score")."""

    UP = "up"
    DOWN = "down"
    STABLE = "stable"
    RISK = "risk"
    OPPORTUNITY = "opportunity"
    ANOMALY = "anomaly"


@dataclass(frozen=True, slots=True)
class BusinessSignal:
    """Résultat analytique brut d'une capacité IA, avant toute interprétation métier."""

    company_id: UUID
    module_code: str
    task_code: str
    capability: str
    entity: str
    metric: str
    value: float
    direction: SignalDirection
    confidence: float
    previous_value: float | None = None
    expected_value: float | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RecommendedAction:
    """Action suggérée — jamais exécutée automatiquement dans cette phase."""

    type: str
    title: str
    description: str
    expected_impact: Severity
    urgency: Severity
    requires_approval: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BusinessInsight:
    """Fait métier compréhensible, sans jargon ML, dérivé d'un ou plusieurs signaux."""

    title: str
    summary: str
    capability: str
    reasons: tuple[str, ...]
    severity: Severity
    confidence: float
    signals: tuple[BusinessSignal, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DecisionContext:
    """Contexte métier disponible au moment du scoring (tendance, historique...)."""

    company_id: UUID
    module_code: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    historical_trend: Mapping[str, float] = field(default_factory=dict)
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BusinessDecision:
    """Ce que le client final voit — jamais de nom de modèle/métrique technique."""

    insight: BusinessInsight
    business_impact: Severity
    urgency: Severity
    priority: Severity
    recommended_actions: tuple[RecommendedAction, ...]
    provenance: Mapping[str, Any]  # interne uniquement : dataset/version/moteur...


@dataclass(frozen=True, slots=True)
class DecisionBundle:
    """Ensemble de décisions déjà classées par priorité, prêt pour l'affichage."""

    company_id: UUID
    module_code: str
    generated_at: datetime
    decisions: tuple[BusinessDecision, ...]
