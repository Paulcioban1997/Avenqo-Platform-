from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class DatasetRelationship(Base):
    """Tenant-scoped, evidence-backed relationship between two datasets."""

    __tablename__ = "dataset_relationships"
    __table_args__ = (
        UniqueConstraint(
            "left_dataset_id",
            "right_dataset_id",
            "canonical_field",
            name="uq_dataset_relationship_pair_field",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    left_dataset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    right_dataset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    left_column: Mapped[str] = mapped_column(String(255), nullable=False)
    right_column: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_field: Mapped[str] = mapped_column(String(255), nullable=False)
    overlap_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    cardinality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )