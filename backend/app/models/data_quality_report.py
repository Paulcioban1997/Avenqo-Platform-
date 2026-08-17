from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base


class DataQualityReport(Base):
    """Décrit la qualité d'un jeu de données avant son ingestion."""

    __tablename__ = "data_quality_reports"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    dataset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    duplicates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_values: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_dates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_values: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    dataset: Mapped["Dataset"] = relationship(back_populates="quality_report")
