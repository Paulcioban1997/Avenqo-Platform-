from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class MemoryScope(str, Enum):
    USER = "user"
    COMPANY = "company"


class MemoryType(str, Enum):
    PREFERENCE = "preference"
    GOAL = "goal"
    DECISION = "decision"
    PROCEDURE = "procedure"
    KNOWLEDGE = "knowledge"
    SEMANTIC = "semantic"


class AIEnterpriseMemory(TimestampMixin, Base):
    __tablename__ = "ai_enterprise_memories"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    memory_scope: Mapped[str] = mapped_column(String(32), nullable=False, default=MemoryScope.USER.value, index=True)
    memory_type: Mapped[str] = mapped_column(String(64), nullable=False, default=MemoryType.SEMANTIC.value, index=True)
    source_module: Mapped[str] = mapped_column(String(32), nullable=False, default="central", index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
