from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class RetailActiveSource(Base, TimestampMixin):
    __tablename__ = "retail_active_sources"
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_retail_active_source_company"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=True,
    )
    connection_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commerce_connections.id", ondelete="CASCADE"),
        nullable=True,
    )
    selected_source_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )

    @property
    def selection_mode(self) -> str:
        """Returns the normalized selection mode: ALL, CUSTOM_SET, or SINGLE."""
        normalized = (self.source_type or "").upper()
        if normalized in ("ALL", "ALL_SOURCES"):
            return "ALL"
        if normalized in ("CUSTOM_SET", "CUSTOM"):
            return "CUSTOM_SET"
        return "SINGLE"