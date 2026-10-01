from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.ai.chat.chat_service import ChatService
from backend.app.ai.chat.conversation_service import ConversationService
from backend.app.ai.chat.retrieval_service import RetrievalService
from backend.app.ai.llm.factory import LLMProviderFactory
from backend.app.ai.tools.authorization import ToolAuthorizationPolicy
from backend.app.ai.tools.idempotency import AIToolExecutionIdempotencyStore
from backend.app.ai.tools.executor import ToolExecutor
from backend.app.ai.tools.registry import ToolRegistry
from backend.app.ai.usage.policy import AIQuotaPolicy
from backend.app.ai.usage.credit_policy import AvenqoCreditPolicy
from backend.app.ai.usage.service import AIUsageService
from backend.app.config.settings import Settings, get_settings
from backend.app.database import get_db
from backend.app.dependencies.ai_tools import get_business_tool_registry
from backend.app.dependencies.assistants import get_assistant_registry
from backend.app.assistants.registry import AssistantRegistry


def get_conversation_service(db: Session = Depends(get_db)) -> ConversationService:
    return ConversationService(db)


def get_ai_usage_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AIUsageService:
    return AIUsageService(
        db,
        AIQuotaPolicy(settings),
        settings.avenqo_provider_cost_per_credit_usd,
        settings.ai_credit_reservation_ttl_minutes,
        AvenqoCreditPolicy(
            provider_cost_per_credit_usd=settings.avenqo_provider_cost_per_credit_usd,
            minimum_charge_credits=settings.ai_credit_minimum_charge,
            minimum_reserve_credits=settings.ai_credit_minimum_reserve,
            margin_protection_factor=settings.ai_credit_margin_protection_factor,
            max_estimated_provider_cost_usd=settings.ai_max_estimated_provider_cost_usd,
            max_input_tokens_per_request=settings.ai_max_input_tokens_per_request,
            max_output_tokens_per_request=settings.ai_max_output_tokens_per_request,
            max_request_credits=settings.ai_max_request_credits,
        ),
    )


def get_tool_executor(
    registry: ToolRegistry = Depends(get_business_tool_registry),
    agents: AssistantRegistry = Depends(get_assistant_registry),
    db: Session = Depends(get_db),
) -> ToolExecutor:
    return ToolExecutor(
        registry,
        ToolAuthorizationPolicy(db, agents),
        AIToolExecutionIdempotencyStore(db),
    )


def get_chat_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    registry: ToolRegistry = Depends(get_business_tool_registry),
    executor: ToolExecutor = Depends(get_tool_executor),
    usage_service: AIUsageService = Depends(get_ai_usage_service),
) -> ChatService:
    return ChatService(
        ConversationService(db),
        RetrievalService(db),
        LLMProviderFactory.create_gateway(settings),
        tool_registry=registry,
        tool_executor=executor,
        usage_service=usage_service,
        debug_mode=settings.debug,
    )