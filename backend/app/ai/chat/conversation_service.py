from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.chat.exceptions import ConversationNotFoundError
from backend.app.models import AIConversation, AIMessage, AIMessageRole, AIMessageSource


class ConversationService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, tenant_id: UUID, user_id: UUID, title: str) -> AIConversation:
        item = AIConversation(company_id=tenant_id, user_id=user_id, title=title)
        self._db.add(item); self._db.commit(); self._db.refresh(item)
        return item

    def list(self, tenant_id: UUID, user_id: UUID) -> list[AIConversation]:
        return list(self._db.scalars(select(AIConversation).where(AIConversation.company_id == tenant_id, AIConversation.user_id == user_id).order_by(AIConversation.updated_at.desc())).all())

    def get(self, tenant_id: UUID, user_id: UUID, conversation_id: UUID) -> AIConversation:
        item = self._db.scalar(select(AIConversation).where(AIConversation.id == conversation_id, AIConversation.company_id == tenant_id, AIConversation.user_id == user_id))
        if item is None:
            raise ConversationNotFoundError("Conversation introuvable")
        return item

    def messages(self, tenant_id: UUID, conversation_id: UUID, limit: int = 12) -> list[AIMessage]:
        return list(self._db.scalars(select(AIMessage).where(AIMessage.conversation_id == conversation_id, AIMessage.company_id == tenant_id).order_by(AIMessage.created_at.desc()).limit(limit)).all())[::-1]

    def add_message(self, tenant_id: UUID, conversation_id: UUID, role: AIMessageRole, content: str, provider: str | None = None, model: str | None = None, token_usage: dict[str, object] | None = None) -> AIMessage:
        item = AIMessage(conversation_id=conversation_id, company_id=tenant_id, role=role, content=content, provider=provider, model=model, token_usage=token_usage)
        self._db.add(item); self._db.commit(); self._db.refresh(item)
        return item

    def add_sources(self, tenant_id: UUID, message_id: UUID, sources: list[RetrievedSource]) -> None:
        for source in sources:
            self._db.add(AIMessageSource(message_id=message_id, company_id=tenant_id, source_type=source.source_type, source_identifier=source.identifier, source_metadata={"name": source.name, **source.metadata}))
        self._db.commit()

    def delete(self, tenant_id: UUID, user_id: UUID, conversation_id: UUID) -> None:
        self._db.delete(self.get(tenant_id, user_id, conversation_id)); self._db.commit()