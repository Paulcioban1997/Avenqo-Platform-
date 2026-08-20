from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.ai.chat.chat_service import ChatService
from backend.app.ai.chat.conversation_service import ConversationService
from backend.app.ai.chat.retrieval_service import RetrievalService
from backend.app.ai.llm.factory import LLMProviderFactory
from backend.app.ai.tools.business.registry_factory import build_business_tool_registry
from backend.app.ai.tools.executor import ToolExecutor
from backend.app.ai.tools.registry import ToolRegistry
from backend.app.config.settings import Settings, get_settings
from backend.app.database import get_db
from backend.app.dependencies.ai_engine import get_prediction_service
from backend.app.dependencies.datasets import get_company_dataset_ingestion_service
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from shared.ai_engine.prediction.service import PredictionService


def get_conversation_service(db: Session = Depends(get_db)) -> ConversationService:
    return ConversationService(db)


def get_business_tool_registry(
    db: Session = Depends(get_db),
    ingestion: CompanyDatasetIngestionService = Depends(get_company_dataset_ingestion_service),
    prediction_service: PredictionService = Depends(get_prediction_service),
) -> ToolRegistry:
    return build_business_tool_registry(db, ingestion, prediction_service)


def get_tool_executor(registry: ToolRegistry = Depends(get_business_tool_registry)) -> ToolExecutor:
    return ToolExecutor(registry)


def get_chat_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    registry: ToolRegistry = Depends(get_business_tool_registry),
    executor: ToolExecutor = Depends(get_tool_executor),
) -> ChatService:
    return ChatService(
        ConversationService(db),
        RetrievalService(db),
        LLMProviderFactory.create(settings),
        tool_registry=registry,
        tool_executor=executor,
    )