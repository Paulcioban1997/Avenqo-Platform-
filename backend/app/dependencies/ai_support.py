"""DI Phase 32 — Avenqo Platform Support AI. Mirroir de `dependencies/ai_chat.py`."""

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.ai.llm.factory import LLMProviderFactory
from backend.app.ai.llm.health import ProviderHealthRegistry, get_provider_health_registry
from backend.app.ai.support.chat_service import SupportChatService
from backend.app.ai.support.conversation_service import SupportConversationService
from backend.app.ai.support.retrieval_service import PlatformKnowledgeRetrievalService
from backend.app.ai.tools.executor import ToolExecutor
from backend.app.ai.tools.registry import ToolRegistry
from backend.app.ai.tools.support.registry_factory import build_support_tool_registry
from backend.app.ai.usage.policy import AIQuotaPolicy
from backend.app.ai.usage.service import AIUsageService
from backend.app.config.settings import Settings, get_settings
from backend.app.database import get_db
from backend.app.dependencies.ai_engine import get_prediction_service
from shared.ai_engine.prediction.service import PredictionService


def get_support_conversation_service(db: Session = Depends(get_db)) -> SupportConversationService:
    return SupportConversationService(db)


def get_support_ai_usage_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AIUsageService:
    # Réutilise EXACTEMENT le même service/quota que le Business Copilot
    # (Phase 31) : pas de second système de comptage.
    return AIUsageService(db, AIQuotaPolicy(settings))


def get_support_tool_registry(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    prediction_service: PredictionService = Depends(get_prediction_service),
    health_registry: ProviderHealthRegistry = Depends(get_provider_health_registry),
    usage_service: AIUsageService = Depends(get_support_ai_usage_service),
) -> ToolRegistry:
    return build_support_tool_registry(
        db,
        prediction_service=prediction_service,
        knowledge_root=settings.ai_support_knowledge_root,
        health_registry=health_registry,
        usage_service=usage_service,
    )


def get_support_tool_executor(registry: ToolRegistry = Depends(get_support_tool_registry)) -> ToolExecutor:
    return ToolExecutor(registry)


def get_support_chat_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    registry: ToolRegistry = Depends(get_support_tool_registry),
    executor: ToolExecutor = Depends(get_support_tool_executor),
    usage_service: AIUsageService = Depends(get_support_ai_usage_service),
) -> SupportChatService:
    return SupportChatService(
        SupportConversationService(db),
        PlatformKnowledgeRetrievalService(settings.ai_support_knowledge_root),
        LLMProviderFactory.create_gateway(settings),
        registry,
        executor,
        usage_service=usage_service,
    )
