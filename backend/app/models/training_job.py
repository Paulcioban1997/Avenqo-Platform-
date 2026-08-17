from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, JobStatus


class TrainingJob(Base):
    """Représente un entraînement lié à un jeu de données et une tâche IA."""

    __tablename__ = "training_jobs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ai_job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ai_jobs.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    algorithm: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="training_job_status"),
        nullable=False,
        default=JobStatus.PENDING,
    )
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    f1_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    training_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship(back_populates="training_jobs")
    dataset: Mapped["Dataset"] = relationship(back_populates="training_jobs")
    ai_job: Mapped["AIJob"] = relationship(back_populates="training_job")
    model_registries: Mapped[list["ModelRegistry"]] = relationship(back_populates="training_job")
