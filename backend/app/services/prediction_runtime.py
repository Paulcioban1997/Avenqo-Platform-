"""Point d'entrée unique reliant Model Registry -> prédiction -> décision métier.

Réutilise tel quel `PredictionService` (résolution du modèle actif par
entreprise/module/tâche) et `BusinessDecisionService` (Phase 20) : aucun
second moteur de prédiction, aucun second Model Registry. Le seul rôle de ce
module est l'aiguillage (quel exécuteur charger, quelles règles métier
enregistrer pour ce module) — jamais de logique ML ici.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import ModelRegistry
from backend.app.services.business_signal_bridge import signal_from_prediction
from backend.app.services.forecasting_prediction_executor import ForecastingPredictionExecutor
from backend.app.services.recommendation_prediction_executor import RecommendationPredictionExecutor
from backend.app.services.sklearn_prediction_executor import SklearnPredictionExecutor
from modules.retailsense.decision_policies import register_retail_decision_policies
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.decision_intelligence.action_rules import (
    ActionRuleRegistry,
    build_default_action_registry,
)
from shared.ai_engine.decision_intelligence.contracts import BusinessDecision, DecisionContext
from shared.ai_engine.decision_intelligence.cross_capability import CrossCapabilityRuleRegistry
from shared.ai_engine.decision_intelligence.insight_rules import build_default_insight_registry
from shared.ai_engine.decision_intelligence.service import BusinessDecisionService
from shared.ai_engine.prediction.service import PredictionExecutor, PredictionService

# model_type stocké dans ModelRegistry -> capacité générique attendue par le
# Business Decision Layer (seul endroit où "clustering" devient "segmentation").
_CAPABILITY_BY_MODEL_TYPE: dict[str, str] = {
    "classification": "classification",
    "regression": "regression",
    "clustering": "segmentation",
    "anomaly_detection": "anomaly_detection",
    "forecasting": "forecasting",
    "recommendation": "recommendation",
}

# Un module peut enregistrer ses propres règles cross-capacités/actions (voir
# `modules/retailsense/decision_policies.py`) sans jamais introduire de
# ``if module == "retail"`` dans le cœur générique du Business Decision Layer.
_MODULE_DECISION_POLICY_REGISTRARS: dict[str, Callable[[CrossCapabilityRuleRegistry, ActionRuleRegistry], None]] = {
    "retail": register_retail_decision_policies,
}


def resolve_active_model_type(db: Session, tenant: TenantContext, module_code: str, task_code: str) -> str | None:
    """Lit le `model_type` du modèle actif, ou `None` si aucun modèle n'est actif."""

    row = db.scalar(
        select(ModelRegistry).where(
            ModelRegistry.company_id == tenant.company_id,
            ModelRegistry.module_code == module_code,
            ModelRegistry.task_code == task_code,
            ModelRegistry.is_active.is_(True),
        )
    )
    return row.model_type if row is not None else None


def resolve_executor(model_type: str | None) -> PredictionExecutor:
    """Sélectionne l'exécuteur adapté au type de modèle actif."""

    if model_type == "forecasting":
        return ForecastingPredictionExecutor()
    if model_type == "recommendation":
        return RecommendationPredictionExecutor()
    return SklearnPredictionExecutor()


def build_decision_service(module_code: str) -> BusinessDecisionService:
    """Assemble un `BusinessDecisionService` avec les règles propres à ce module."""

    insight_registry = build_default_insight_registry()
    action_registry = build_default_action_registry()
    cross_capability_registry = CrossCapabilityRuleRegistry()
    registrar = _MODULE_DECISION_POLICY_REGISTRARS.get(module_code)
    if registrar is not None:
        registrar(cross_capability_registry, action_registry)
    return BusinessDecisionService(insight_registry, action_registry, cross_capability_registry)


class PredictionRuntime:
    """Transforme une demande de prédiction en décision métier, sans jargon ML.

    Flux : Model Registry (modèle actif) -> exécuteur -> `BusinessSignal` ->
    `BusinessDecisionService` -> `BusinessDecision` (titre/impact/priorité/action).
    """

    def __init__(self, prediction_service: PredictionService) -> None:
        self._predictions = prediction_service

    def decide(
        self,
        db: Session,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
        features: Mapping[str, Any],
    ) -> BusinessDecision:
        model_type = resolve_active_model_type(db, tenant, module_code, task_code)
        executor = resolve_executor(model_type)
        outcome = self._predictions.predict(tenant, module_code, task_code, features, executor)

        capability = _CAPABILITY_BY_MODEL_TYPE.get(model_type or "", model_type or "unknown")
        entity = str(features.get("entity", task_code))
        previous_value = features.get("previous_value")
        signal = signal_from_prediction(
            tenant.company_id, module_code, task_code, capability, entity, outcome, previous_value
        )

        context = DecisionContext(company_id=tenant.company_id, module_code=module_code)
        bundle = build_decision_service(module_code).build_bundle(context, [signal])
        return bundle.decisions[0]
