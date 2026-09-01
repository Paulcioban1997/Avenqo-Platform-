from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.ai.central.service import CentralAIService
from backend.app.assistants.registry import AssistantRegistry
from backend.app.database import get_db
from backend.app.dependencies.ai_chat import get_ai_usage_service, get_chat_service
from backend.app.dependencies.assistants import get_assistant_registry
from backend.app.repositories.module_entitlements import SQLAlchemyModuleEntitlements
from modules.entitlements import ModuleAccessService


def get_central_ai_service(
    db: Session = Depends(get_db),
    registry: AssistantRegistry = Depends(get_assistant_registry),
    chat_service=Depends(get_chat_service),
    usage_service=Depends(get_ai_usage_service),
) -> CentralAIService:
    return CentralAIService(
        registry,
        chat_service,
        usage_service,
        ModuleAccessService(SQLAlchemyModuleEntitlements(db)),
    )