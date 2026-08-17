"""Business Opportunity Engine (Phase 25).

Dernier maillon de la chaîne :

    BusinessSignal -> BusinessInsight -> BusinessDecision -> BusinessOpportunity

Transforme les `BusinessDecision` déjà priorisées (`BusinessDecisionService`,
`rank_decisions()`) en une liste d'opportunités 100% métier, compréhensible
par un propriétaire de boutique — jamais un second moteur de scoring/ranking
concurrent : `priority`/`severity` proviennent tels quels de la couche
Decision Intelligence existante (`compute_priority`/`compute_severity`).

Aucune persistance ici (voir rapport Phase 25, section "Persistence") : les
opportunités sont calculées à la demande, exactement comme
`/portfolio-decisions` (Phase 22/24), jamais stockées en base.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping, Sequence
from uuid import UUID, uuid4

from shared.ai_engine.decision_intelligence.contracts import (
    BusinessDecision,
    BusinessSignal,
    DecisionBundle,
    Severity,
    SignalDirection,
)


class OpportunityStatus(StrEnum):
    """Cycle de vie conceptuel d'une opportunité — aucune exécution automatique.

    Phase 25 ne persiste pas les opportunités (calcul à la demande) : chaque
    appel régénère donc systématiquement `NEW`. Les autres valeurs existent
    pour que le modèle soit prêt le jour où une persistance sera ajoutée
    (voir rapport, section Persistence).
    """

    NEW = "new"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"
    ACTIONED = "actioned"


@dataclass(frozen=True, slots=True)
class BusinessOpportunity:
    """Opportunité métier exploitable — jamais de jargon ML, jamais de montant inventé."""

    id: UUID
    company_id: UUID
    capability: str
    title: str
    summary: str
    direction: SignalDirection
    priority: Severity
    severity: Severity
    confidence: float
    estimated_impact: float | None
    impact_unit: str | None
    recommended_action: str
    status: OpportunityStatus
    source_signals: tuple[str, ...]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=dict)


# Signaux "sans phénomène notable" : jamais transformés en opportunité (une
# demande/un prix/un segment parfaitement stable est une information, pas une
# opportunité à afficher en priorité — voir Phase 25, point 10).
_NON_OPPORTUNITY_DIRECTIONS = frozenset({SignalDirection.STABLE})

# Capacité IA -> étiquette métier affichée (capability = fonction métier,
# jamais famille d'algorithme). "classification" reste partagé par
# bad_review/churn (Phase 21/24) : désambiguïsé via task_code.
_CAPABILITY_LABELS: dict[str, str] = {
    "forecasting": "weekly_forecast",
    "anomaly_detection": "anomaly",
    "sentiment_analysis": "sentiment",
    "cross_capability.churn_segmentation": "churn",
    "cross_capability.customer_risk": "segmentation",
    "cross_capability.stock_risk": "weekly_forecast",
}


def _opportunity_capability(decision: BusinessDecision) -> str:
    insight = decision.insight
    if insight.capability == "classification" and insight.signals:
        return insight.signals[0].task_code
    return _CAPABILITY_LABELS.get(insight.capability, insight.capability)


def _signal_key(signal: BusinessSignal) -> str:
    """Clé naturelle et déterministe : les signaux ne sont jamais persistés

    (aucun id de base de données), recalculés à chaque appel."""

    return f"{signal.task_code}:{signal.metric}:{signal.entity}"


def _is_opportunity_worthy(decision: BusinessDecision) -> bool:
    directions = {signal.direction for signal in decision.insight.signals}
    return not directions.issubset(_NON_OPPORTUNITY_DIRECTIONS)


def _percent_change(value: float, previous_value: float | None) -> float | None:
    if previous_value in (None, 0):
        return None
    return round(((value - previous_value) / abs(previous_value)) * 100, 1)


def _estimate_impact(decision: BusinessDecision) -> tuple[float | None, str | None]:
    """Impact réellement calculable à partir des données disponibles.

    Jamais de montant financier inventé : uniquement des pourcentages de
    variation réelle, des comptages de clients réels, ou aucune estimation
    (`None`) lorsque la capacité ne fournit pas de mesure agrégée fiable.
    """

    capability = _opportunity_capability(decision)
    insight = decision.insight

    if capability in ("demand", "price", "weekly_forecast"):
        signal = insight.signals[0]
        change = _percent_change(signal.value, signal.previous_value)
        return (change, "percent") if change is not None else (None, None)

    if capability == "recommendation":
        signal = insight.signals[0]
        if signal.direction == SignalDirection.OPPORTUNITY:
            return float(signal.value), "customers"
        return None, None

    if capability == "churn":
        segmentation_signal = next(
            (s for s in insight.signals if s.capability == "segmentation"), None
        )
        if segmentation_signal is not None and segmentation_signal.value > 0:
            return float(int(segmentation_signal.value)), "customers"
        return None, None

    if capability == "segmentation":
        signal = insight.signals[0]
        if signal.metric == "segment_share":
            return round(signal.value * 100, 1), "percent"
        if signal.value > 0:
            return float(int(signal.value)), "customers"
        return None, None

    if capability == "sentiment":
        signal = insight.signals[0]
        return round(signal.value * 100, 1), "percent"

    # bad_review (classification, prédiction unitaire) et anomaly_detection :
    # la valeur brute est un score/une probabilité, jamais un agrégat métier
    # fiable -> aucune estimation inventée.
    return None, None


def _shares_signal(a: BusinessDecision, b: BusinessDecision) -> bool:
    """Comparaison par identité d'objet (jamais par égalité/hash) : `metadata`

    peut contenir un dict non-hashable, et deux signaux distincts peuvent
    avoir des valeurs identiques sans décrire le même événement."""

    a_ids = {id(signal) for signal in a.insight.signals}
    return any(id(signal) in a_ids for signal in b.insight.signals)


def _representative_signal(signals: Sequence[BusinessSignal]) -> BusinessSignal:
    """Même critère que `BusinessDecisionService._build_decision` (le signal le

    plus fiable de l'insight) — jamais un second calcul divergent."""

    return max(signals, key=lambda signal: signal.confidence)


def deduplicate_decisions(decisions: Sequence[BusinessDecision]) -> tuple[BusinessDecision, ...]:
    """Un seul phénomène métier ne doit jamais produire deux opportunités.

    Critère déterministe (Phase 25, point 17) : deux décisions qui partagent
    au moins un `BusinessSignal` source identique décrivent le même
    phénomène (même tenant implicite, même signal, même entité/segment) — on
    ne garde alors que la plus spécifique (une décision cross-capability
    l'emporte toujours sur une décision générique par signal isolé). Ne
    fusionne jamais deux décisions qui ne partagent aucun signal commun,
    même si leurs capacités semblent liées (ex. demand/weekly_forecast).
    """

    kept: list[BusinessDecision] = []
    for decision in decisions:
        is_combo = decision.insight.capability.startswith("cross_capability.")
        duplicate_index = next(
            (index for index, existing in enumerate(kept) if _shares_signal(decision, existing)), None
        )
        if duplicate_index is None:
            kept.append(decision)
            continue
        existing_is_combo = kept[duplicate_index].insight.capability.startswith("cross_capability.")
        if is_combo and not existing_is_combo:
            kept[duplicate_index] = decision
    return tuple(kept)


class BusinessOpportunityService:
    """Convertit un `DecisionBundle` déjà priorisé en `BusinessOpportunity`.

    Ne recalcule ni priorité ni ranking : réutilise tels quels
    `BusinessDecision.priority`/`insight.severity` et l'ordre de
    `rank_decisions()` (aucun second moteur concurrent).
    """

    def from_bundle(self, bundle: DecisionBundle) -> tuple[BusinessOpportunity, ...]:
        worthy = [decision for decision in bundle.decisions if _is_opportunity_worthy(decision)]
        deduplicated = deduplicate_decisions(worthy)
        return tuple(self._to_opportunity(bundle.company_id, decision) for decision in deduplicated)

    def _to_opportunity(self, company_id: UUID, decision: BusinessDecision) -> BusinessOpportunity:
        insight = decision.insight
        action = decision.recommended_actions[0]
        estimated_impact, impact_unit = _estimate_impact(decision)
        representative = _representative_signal(insight.signals)
        return BusinessOpportunity(
            id=uuid4(),
            company_id=company_id,
            capability=_opportunity_capability(decision),
            title=insight.title,
            summary=insight.summary,
            direction=representative.direction,
            priority=decision.priority,
            severity=insight.severity,
            confidence=insight.confidence,
            estimated_impact=estimated_impact,
            impact_unit=impact_unit,
            recommended_action=f"{action.title} — {action.description}",
            status=OpportunityStatus.NEW,
            source_signals=tuple(_signal_key(signal) for signal in insight.signals),
        )
