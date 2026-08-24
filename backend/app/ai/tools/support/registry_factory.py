"""Construction du registre d'outils du Support AI Avenqo (Phase 32).

Registre STRICTEMENT séparé de `build_business_tool_registry` (Business
Copilot) : aucun outil métier/prédictif n'y est jamais enregistré.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.ai.llm.health import ProviderHealthRegistry
from backend.app.ai.support.retrieval_service import PlatformKnowledgeRetrievalService
from backend.app.ai.tools.registry import ToolRegistry
from backend.app.ai.tools.support.support_tools import (
    GetAICapabilityStatusTool,
    GetAvailableFeaturesTool,
    GetBillingStatusTool,
    GetConnectionStatusTool,
    GetCurrentPlanTool,
    SearchAvenqoDocsTool,
)
from backend.app.ai.usage.service import AIUsageService
from shared.ai_engine.prediction.service import PredictionService


def build_support_tool_registry(
    session: Session,
    *,
    prediction_service: PredictionService,
    knowledge_root: str,
    health_registry: ProviderHealthRegistry,
    usage_service: AIUsageService,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(SearchAvenqoDocsTool(PlatformKnowledgeRetrievalService(knowledge_root)))
    registry.register(GetCurrentPlanTool(session))
    registry.register(GetAvailableFeaturesTool(session, prediction_service))
    registry.register(GetConnectionStatusTool(session))
    registry.register(GetAICapabilityStatusTool(health_registry))
    registry.register(GetBillingStatusTool(session, usage_service))
    return registry
