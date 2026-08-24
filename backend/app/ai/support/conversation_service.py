"""Persistance des conversations du Support AI (Phase 32).

Mirroir volontaire de `backend/app/ai/chat/conversation_service.py` mais sur
les tables `ai_support_*`, physiquement séparées des conversations Business
Copilot — jamais de mélange entre les deux historiques.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.chat.exceptions import ConversationNotFoundError
from backend.app.ai.chat.source_service import RetrievedSource
from backend.app.models import AIMessageRole, AISupportConversation, AISupportMessage, AISupportMessageSource


class SupportConversationService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, tenant_id: UUID, user_id: UUID, title: str) -> AISupportConversation:
        item = AISupportConversation(company_id=tenant_id, user_id=user_id, title=title)
        self._db.add(item); self._db.commit(); self._db.refresh(item)
        return item

    def list(self, tenant_id: UUID, user_id: UUID) -> list[AISupportConversation]:
        return list(self._db.scalars(select(AISupportConversation).where(AISupportConversation.company_id == tenant_id, AISupportConversation.user_id == user_id).order_by(AISupportConversation.updated_at.desc())).all())

    def get(self, tenant_id: UUID, user_id: UUID, conversation_id: UUID) -> AISupportConversation:
        item = self._db.scalar(select(AISupportConversation).where(AISupportConversation.id == conversation_id, AISupportConversation.company_id == tenant_id, AISupportConversation.user_id == user_id))
        if item is None:
            raise ConversationNotFoundError("Conversation introuvable")
        return item

    def messages(self, tenant_id: UUID, conversation_id: UUID, limit: int = 12) -> list[AISupportMessage]:
        return list(self._db.scalars(select(AISupportMessage).where(AISupportMessage.conversation_id == conversation_id, AISupportMessage.company_id == tenant_id).order_by(AISupportMessage.created_at.desc()).limit(limit)).all())[::-1]

    def add_message(self, tenant_id: UUID, conversation_id: UUID, role: AIMessageRole, content: str, provider: str | None = None, model: str | None = None, token_usage: dict[str, object] | None = None) -> AISupportMessage:
        item = AISupportMessage(conversation_id=conversation_id, company_id=tenant_id, role=role, content=content, provider=provider, model=model, token_usage=token_usage)
        self._db.add(item); self._db.commit(); self._db.refresh(item)
        return item

    def add_sources(self, tenant_id: UUID, message_id: UUID, sources: list[RetrievedSource]) -> None:
        for source in sources:
            self._db.add(AISupportMessageSource(message_id=message_id, company_id=tenant_id, source_type=source.source_type, source_identifier=source.identifier, source_metadata={"name": source.name, **source.metadata}))
        self._db.commit()

    def delete(self, tenant_id: UUID, user_id: UUID, conversation_id: UUID) -> None:
        self._db.delete(self.get(tenant_id, user_id, conversation_id)); self._db.commit()
