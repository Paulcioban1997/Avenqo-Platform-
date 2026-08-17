"""Point d'entrée unique du Business Decision Intelligence Layer.

Générique à tout Avenqo (RetailSenseAI, CRM AI, Accounting AI, Marketing
AI...) : aucune logique de module ici, uniquement l'orchestration
signal -> insight -> decision -> action, plus l'agrégation multi-capacités via
les registres injectés (vides par défaut au niveau générique).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from shared.ai_engine.decision_intelligence.action_rules import (
    ActionRuleRegistry,
    build_default_action_registry,
)
from shared.ai_engine.decision_intelligence.contracts import (
    BusinessDecision,
    BusinessInsight,
    BusinessSignal,
    DecisionBundle,
    DecisionContext,
)
from shared.ai_engine.decision_intelligence.cross_capability import CrossCapabilityRuleRegistry
from shared.ai_engine.decision_intelligence.insight_rules import (
    InsightRuleRegistry,
    build_default_insight_registry,
)
from shared.ai_engine.decision_intelligence.prioritization import rank_decisions
from shared.ai_engine.decision_intelligence.scoring import (
    compute_business_impact,
    compute_priority,
    compute_urgency,
)

_ENGINE_VERSION = "decision-intelligence-v1"


class BusinessDecisionService:
    """Transforme des `BusinessSignal` en `DecisionBundle` priorisé et traçable."""

    def __init__(
        self,
        insight_registry: InsightRuleRegistry | None = None,
        action_registry: ActionRuleRegistry | None = None,
        cross_capability_registry: CrossCapabilityRuleRegistry | None = None,
    ) -> None:
        self._insights = insight_registry or build_default_insight_registry()
        self._actions = action_registry or build_default_action_registry()
        self._cross_capability = cross_capability_registry or CrossCapabilityRuleRegistry()

    def build_bundle(
        self,
        context: DecisionContext,
        signals: Sequence[BusinessSignal],
    ) -> DecisionBundle:
        decisions: list[BusinessDecision] = []

        for signal in signals:
            insight = self._insights.build(signal)
            decisions.append(self._build_decision(insight, context))

        for insight in self._cross_capability.evaluate(signals):
            decisions.append(self._build_decision(insight, context))

        return DecisionBundle(
            company_id=context.company_id,
            module_code=context.module_code,
            generated_at=datetime.now(timezone.utc),
            decisions=rank_decisions(decisions),
        )

    def _build_decision(self, insight: BusinessInsight, context: DecisionContext) -> BusinessDecision:
        representative_signal = max(insight.signals, key=lambda signal: signal.confidence)
        business_impact = compute_business_impact(representative_signal, context)
        urgency = compute_urgency(representative_signal, context)
        priority = compute_priority(insight.severity, business_impact, urgency, insight.confidence)
        action = self._actions.build(insight)

        provenance = {
            "company_id": str(context.company_id),
            "module_code": context.module_code,
            "decision_engine_version": _ENGINE_VERSION,
            "generated_at": context.generated_at.isoformat(),
            "signals": [
                {
                    "task_code": signal.task_code,
                    "capability": signal.capability,
                    "entity": signal.entity,
                    "metric": signal.metric,
                    "value": signal.value,
                    "timestamp": signal.timestamp.isoformat(),
                }
                for signal in insight.signals
            ],
        }
        return BusinessDecision(
            insight=insight,
            business_impact=business_impact,
            urgency=urgency,
            priority=priority,
            recommended_actions=(action,),
            provenance=provenance,
        )
