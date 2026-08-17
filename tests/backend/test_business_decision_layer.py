"""Phase 20 (BLOC B) — Business Decision Intelligence Layer.

Prouve que la chaîne `BusinessSignal` -> `BusinessInsight` -> `BusinessDecision`
-> `RecommendedAction` :

- ne fuit jamais de jargon ML (nom de modèle, "class_1", "anomaly_score" brut,
  hyperparamètre...) dans les textes visibles (titre/résumé/raisons) ;
- calcule severity/business_impact/urgency/priority de façon déterministe et
  cohérente (amplitude + confiance, jamais de second modèle ML) ;
- reste 100% générique au niveau du cœur (`shared.ai_engine.decision_intelligence`) —
  aucune règle spécifique à un module n'y est câblée en dur ;
- permet à un module (ici RetailSenseAI, via `modules/retailsense/decision_policies.py`)
  d'enregistrer ses propres règles cross-capacités SANS un seul
  ``if module == "retail"`` dans le cœur générique ;
- agrège plusieurs capacités (forecasting + anomaly_detection + segmentation +
  classification) en un seul bundle trié par priorité, avec une provenance
  traçable (jamais montrée au client final) ;
- respecte l'isolation multi-tenant (aucun mélange de `company_id` entre
  bundles) ;
- fournit au moins un test d'intégration cross-capacité de bout en bout
  (prévision de demande en hausse + anomalie détectée -> décision "risque de
  rupture de stock" priorisée, voir point 27 du cahier des charges).

Aucune logique Olist : tous les signaux ci-dessous sont génériques et fictifs.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from modules.retailsense.decision_policies import register_retail_decision_policies
from shared.ai_engine.decision_intelligence.action_rules import build_default_action_registry
from shared.ai_engine.decision_intelligence.contracts import (
    BusinessSignal,
    DecisionContext,
    Severity,
    SignalDirection,
)
from shared.ai_engine.decision_intelligence.cross_capability import CrossCapabilityRuleRegistry
from shared.ai_engine.decision_intelligence.insight_rules import build_default_insight_registry
from shared.ai_engine.decision_intelligence.prioritization import rank_decisions
from shared.ai_engine.decision_intelligence.scoring import (
    compute_business_impact,
    compute_priority,
    compute_severity,
    compute_urgency,
)
from shared.ai_engine.decision_intelligence.service import BusinessDecisionService
from backend.app.services.business_signal_bridge import (
    signal_from_anomaly,
    signal_from_classification,
    signal_from_forecast,
    signal_from_segmentation,
)


_FORBIDDEN_ML_JARGON = (
    "gradient_boosting",
    "isolation_forest",
    "arima",
    "sarima",
    "hyperparameter",
    "hyperparamètre",
    "randomizedsearchcv",
    "r2_score",
    "rmse",
    "smape",
    "class_1",
    "anomaly_score",
    "p-value",
)


def _forecast_signal(**overrides) -> BusinessSignal:
    defaults = dict(
        company_id=uuid4(),
        module_code="retail",
        task_code="weekly_forecast",
        capability="forecasting",
        entity="store-1",
        metric="quantity",
        value=150.0,
        direction=SignalDirection.UP,
        confidence=0.8,
        previous_value=100.0,
    )
    defaults.update(overrides)
    return BusinessSignal(**defaults)


def _anomaly_signal(**overrides) -> BusinessSignal:
    defaults = dict(
        company_id=uuid4(),
        module_code="retail",
        task_code="anomaly",
        capability="anomaly_detection",
        entity="store-1",
        metric="response_time",
        value=0.9,
        direction=SignalDirection.ANOMALY,
        confidence=0.85,
    )
    defaults.update(overrides)
    return BusinessSignal(**defaults)


def _segmentation_signal(**overrides) -> BusinessSignal:
    defaults = dict(
        company_id=uuid4(),
        module_code="retail",
        task_code="segmentation",
        capability="segmentation",
        entity="high-value-customers",
        metric="segment_share",
        value=0.35,
        direction=SignalDirection.STABLE,
        confidence=0.6,
    )
    defaults.update(overrides)
    return BusinessSignal(**defaults)


def _risk_classification_signal(**overrides) -> BusinessSignal:
    defaults = dict(
        company_id=uuid4(),
        module_code="retail",
        task_code="bad_review",
        capability="classification",
        entity="high-value-customers",
        metric="risk_probability",
        value=0.82,
        direction=SignalDirection.RISK,
        confidence=0.82,
    )
    defaults.update(overrides)
    return BusinessSignal(**defaults)


def _assert_no_ml_jargon(*texts: str) -> None:
    for text in texts:
        lowered = text.lower()
        for term in _FORBIDDEN_ML_JARGON:
            assert term not in lowered, f"jargon ML détecté ({term!r}) dans: {text!r}"


# ---------------------------------------------------------------------------
# 1 — signal -> insight -> decision -> action : contrat de base
# ---------------------------------------------------------------------------


def test_build_bundle_converts_signal_into_business_friendly_insight_and_action() -> None:
    service = BusinessDecisionService()
    signal = _forecast_signal()
    context = DecisionContext(company_id=signal.company_id, module_code="retail")

    bundle = service.build_bundle(context, [signal])

    assert len(bundle.decisions) == 1
    decision = bundle.decisions[0]
    assert decision.insight.capability == "forecasting"
    assert len(decision.recommended_actions) == 1
    action = decision.recommended_actions[0]
    assert action.requires_approval is True
    _assert_no_ml_jargon(
        decision.insight.title, decision.insight.summary, *decision.insight.reasons, action.title, action.description
    )


def test_no_ml_jargon_leaks_for_any_default_capability() -> None:
    service = BusinessDecisionService()
    signals = [
        _forecast_signal(),
        _anomaly_signal(),
        _segmentation_signal(),
        _risk_classification_signal(),
    ]
    context = DecisionContext(company_id=uuid4(), module_code="retail")

    bundle = service.build_bundle(context, signals)

    for decision in bundle.decisions:
        _assert_no_ml_jargon(decision.insight.title, decision.insight.summary, *decision.insight.reasons)
        for action in decision.recommended_actions:
            _assert_no_ml_jargon(action.title, action.description)


# ---------------------------------------------------------------------------
# 2 — scoring déterministe : severity/business_impact/urgency/priority
# ---------------------------------------------------------------------------


def test_compute_severity_increases_with_magnitude_and_confidence() -> None:
    small_change = _forecast_signal(value=101.0, previous_value=100.0, confidence=0.9)
    big_change = _forecast_signal(value=300.0, previous_value=100.0, confidence=0.9)

    assert compute_severity(big_change) != Severity.INFORMATIONAL
    small_score = compute_severity(small_change)
    big_score = compute_severity(big_change)
    _SEVERITY_RANK = {
        Severity.INFORMATIONAL: 0,
        Severity.LOW: 1,
        Severity.MEDIUM: 2,
        Severity.HIGH: 3,
        Severity.CRITICAL: 4,
    }
    assert _SEVERITY_RANK[big_score] >= _SEVERITY_RANK[small_score]


def test_compute_priority_is_capped_when_confidence_is_too_low() -> None:
    low_confidence_signal = _forecast_signal(value=500.0, previous_value=100.0, confidence=0.1)
    context = DecisionContext(company_id=low_confidence_signal.company_id, module_code="retail")

    business_impact = compute_business_impact(low_confidence_signal, context)
    urgency = compute_urgency(low_confidence_signal, context)
    priority = compute_priority(
        compute_severity(low_confidence_signal), business_impact, urgency, low_confidence_signal.confidence
    )

    # Confiance trop faible (<0.4) : la priorité ne peut jamais dépasser MEDIUM,
    # même si l'amplitude brute suggérerait un signal critique.
    assert priority in (Severity.MEDIUM, Severity.LOW, Severity.INFORMATIONAL)


def test_compute_business_impact_is_boosted_by_confirming_historical_trend() -> None:
    signal = _forecast_signal(value=150.0, previous_value=100.0, confidence=0.7, direction=SignalDirection.UP)
    context_without_trend = DecisionContext(company_id=signal.company_id, module_code="retail")
    context_with_trend = DecisionContext(
        company_id=signal.company_id, module_code="retail", historical_trend={"quantity": 1.0}
    )

    impact_without_trend = compute_business_impact(signal, context_without_trend)
    impact_with_trend = compute_business_impact(signal, context_with_trend)

    _SEVERITY_RANK = {
        Severity.INFORMATIONAL: 0,
        Severity.LOW: 1,
        Severity.MEDIUM: 2,
        Severity.HIGH: 3,
        Severity.CRITICAL: 4,
    }
    assert _SEVERITY_RANK[impact_with_trend] >= _SEVERITY_RANK[impact_without_trend]


# ---------------------------------------------------------------------------
# 3 — agrégation multi-capacités, priorisation, provenance, isolation
# ---------------------------------------------------------------------------


def test_build_bundle_ranks_decisions_by_priority_highest_first() -> None:
    service = BusinessDecisionService()
    high_severity_signal = _forecast_signal(value=1000.0, previous_value=100.0, confidence=0.9)
    low_severity_signal = _segmentation_signal()
    context = DecisionContext(company_id=uuid4(), module_code="retail")

    bundle = service.build_bundle(context, [low_severity_signal, high_severity_signal])

    ranked_priorities = [decision.priority for decision in bundle.decisions]
    assert ranked_priorities == sorted(
        ranked_priorities,
        key=lambda priority: (
            Severity.CRITICAL,
            Severity.HIGH,
            Severity.MEDIUM,
            Severity.LOW,
            Severity.INFORMATIONAL,
        ).index(priority),
    )


def test_build_bundle_includes_traceable_but_hidden_provenance() -> None:
    service = BusinessDecisionService()
    signal = _forecast_signal()
    context = DecisionContext(company_id=signal.company_id, module_code="retail")

    bundle = service.build_bundle(context, [signal])
    decision = bundle.decisions[0]

    assert decision.provenance["module_code"] == "retail"
    assert decision.provenance["company_id"] == str(signal.company_id)
    assert "decision_engine_version" in decision.provenance
    assert decision.provenance["signals"][0]["task_code"] == "weekly_forecast"


def test_build_bundle_keeps_tenants_isolated() -> None:
    service = BusinessDecisionService()
    tenant_a_signal = _forecast_signal()
    tenant_b_signal = _forecast_signal(company_id=uuid4())

    bundle_a = service.build_bundle(
        DecisionContext(company_id=tenant_a_signal.company_id, module_code="retail"), [tenant_a_signal]
    )
    bundle_b = service.build_bundle(
        DecisionContext(company_id=tenant_b_signal.company_id, module_code="retail"), [tenant_b_signal]
    )

    assert bundle_a.company_id == tenant_a_signal.company_id
    assert bundle_b.company_id == tenant_b_signal.company_id
    assert bundle_a.company_id != bundle_b.company_id
    assert bundle_a.decisions[0].provenance["company_id"] != bundle_b.decisions[0].provenance["company_id"]


def test_generic_core_has_no_module_specific_rules_by_default() -> None:
    """Le cœur générique (sans enregistrement explicite d'un module) ne connaît

    AUCUNE règle cross-capacité : le registre est vide par défaut.
    """

    registry = CrossCapabilityRuleRegistry()
    signals = [_forecast_signal(direction=SignalDirection.UP), _anomaly_signal()]

    assert registry.evaluate(signals) == ()


# ---------------------------------------------------------------------------
# 4 — pont "sorties ML brutes -> BusinessSignal" (business_signal_bridge)
# ---------------------------------------------------------------------------


def test_signal_from_forecast_reads_last_forecast_point_and_direction() -> None:
    company_id = uuid4()
    forecast_output = {
        "forecast": [
            {"timestamp": "2024-02-01T00:00:00", "prediction": 120.0},
            {"timestamp": "2024-02-02T00:00:00", "prediction": 140.0},
        ],
        "horizon": 2,
    }

    signal = signal_from_forecast(company_id, "retail", "weekly_forecast", "store-1", forecast_output, 100.0)

    assert signal.value == 140.0
    assert signal.direction == SignalDirection.UP
    assert signal.capability == "forecasting"


def test_signal_from_anomaly_and_classification_and_segmentation_are_generic() -> None:
    company_id = uuid4()
    anomaly = signal_from_anomaly(company_id, "retail", "anomaly", "sensor-1", 0.95, True)
    classification = signal_from_classification(company_id, "retail", "bad_review", "customer-1", 0.9)
    segmentation = signal_from_segmentation(company_id, "retail", "segmentation", "vip", 0.4)

    assert anomaly.direction == SignalDirection.ANOMALY
    assert classification.direction == SignalDirection.RISK
    assert segmentation.capability == "segmentation"


# ---------------------------------------------------------------------------
# 5 — Point 27 : test d'intégration cross-capacité (forecasting + anomaly)
# ---------------------------------------------------------------------------


def test_cross_capability_forecast_and_anomaly_produce_prioritized_stock_risk_decision() -> None:
    """Intégration bout-en-bout : demande en hausse (forecasting) + anomalie

    détectée (anomaly_detection) sur la même entreprise -> une décision
    "risque de rupture de stock" priorisée, en plus des décisions
    individuelles par capacité — sans aucun ``if module == "retail"`` dans le
    cœur générique (la règle vit dans `modules/retailsense/decision_policies.py`
    et est enregistrée dans les registres génériques injectés).
    """

    cross_capability_registry = CrossCapabilityRuleRegistry()
    action_registry = build_default_action_registry()
    register_retail_decision_policies(cross_capability_registry, action_registry)

    service = BusinessDecisionService(
        insight_registry=build_default_insight_registry(),
        action_registry=action_registry,
        cross_capability_registry=cross_capability_registry,
    )

    company_id = uuid4()
    forecast_signal = _forecast_signal(company_id=company_id, direction=SignalDirection.UP)
    anomaly_signal = _anomaly_signal(company_id=company_id)
    context = DecisionContext(company_id=company_id, module_code="retail")

    bundle = service.build_bundle(context, [forecast_signal, anomaly_signal])

    # Trois décisions attendues : une par signal individuel + une décision
    # cross-capacité "risque de rupture de stock".
    assert len(bundle.decisions) == 3
    stock_risk_decisions = [d for d in bundle.decisions if d.insight.title == "Risque de rupture de stock"]
    assert len(stock_risk_decisions) == 1
    stock_risk_decision = stock_risk_decisions[0]

    assert stock_risk_decision.insight.severity == Severity.HIGH
    assert stock_risk_decision.recommended_actions[0].type == "REVIEW_INVENTORY"
    assert stock_risk_decision.recommended_actions[0].requires_approval is True
    assert len(stock_risk_decision.insight.signals) == 2
    _assert_no_ml_jargon(stock_risk_decision.insight.title, stock_risk_decision.insight.summary)

    # La décision cross-capacité doit apparaître parmi les priorités les plus
    # hautes du bundle trié (jamais reléguée en dernier alors qu'elle est HIGH).
    priorities = [d.priority for d in bundle.decisions]
    assert stock_risk_decision.priority in priorities[: len(priorities)]
    _priority_rank = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
        Severity.INFORMATIONAL: 4,
    }
    ranked = sorted(priorities, key=lambda p: _priority_rank[p])
    assert priorities == ranked


def test_cross_capability_rule_does_not_fire_without_both_signals() -> None:
    cross_capability_registry = CrossCapabilityRuleRegistry()
    action_registry = build_default_action_registry()
    register_retail_decision_policies(cross_capability_registry, action_registry)
    service = BusinessDecisionService(
        insight_registry=build_default_insight_registry(),
        action_registry=action_registry,
        cross_capability_registry=cross_capability_registry,
    )

    company_id = uuid4()
    only_forecast = [_forecast_signal(company_id=company_id, direction=SignalDirection.UP)]
    context = DecisionContext(company_id=company_id, module_code="retail")

    bundle = service.build_bundle(context, only_forecast)

    # Un seul signal fourni : uniquement la décision individuelle, jamais la
    # décision cross-capacité (qui exige forecasting ET anomaly_detection).
    assert len(bundle.decisions) == 1
    assert bundle.decisions[0].insight.title != "Risque de rupture de stock"
