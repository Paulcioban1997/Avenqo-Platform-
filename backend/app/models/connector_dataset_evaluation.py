from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, DatasetEvaluationStatus


class ConnectorDatasetEvaluation(Base):
    """One durable, tenant/source-scoped AI evaluation per dataset generation."""

    __tablename__ = "connector_dataset_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "connection_id",
            "dataset_id",
            "dataset_generation",
            name="uq_connector_dataset_evaluation_generation",
        ),
        Index(
            "ix_connector_dataset_evaluations_due",
            "status",
            "due_at",
            "lease_expires_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connection_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commerce_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    changed_records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[DatasetEvaluationStatus] = mapped_column(
        SAEnum(DatasetEvaluationStatus, name="dataset_evaluation_status"),
        nullable=False,
        default=DatasetEvaluationStatus.PENDING,
        index=True,
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    drift_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_job_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )