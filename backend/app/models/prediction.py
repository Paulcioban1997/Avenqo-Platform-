from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base


class Prediction(Base):
    """Représente une prédiction produite par un modèle enregistré."""

    __tablename__ = "predictions"

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
    model_registry_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_registries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    prediction: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    company: Mapped["Company"] = relationship(back_populates="predictions")
    model_registry: Mapped["ModelRegistry"] = relationship(back_populates="predictions")
