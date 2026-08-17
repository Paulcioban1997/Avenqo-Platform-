from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base


class ModelRegistry(Base):
    """Référence un modèle entraîné et sauvegardé dans le registre."""

    __tablename__ = "model_registries"

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
    training_job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("training_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Phase 18.2 : plusieurs tâches automatiques peuvent désormais tourner en
    # parallèle pour la même entreprise (une par capacité détectée dans les
    # données) — ces deux colonnes permettent de scoper "le modèle actif" par
    # (entreprise, module, tâche) au lieu d'une seule ligne active par entreprise.
    module_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    task_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_type: Mapped[str] = mapped_column(String(120), nullable=False)
    framework: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    metric: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    # Nombre de lignes du dataset utilisé pour cet entraînement — permet à la
    # Phase 8 (Auto Retraining) de détecter un volume important de nouvelles
    # données depuis le dernier entraînement, sans dépendre du ModelRegistry
    # de l'AI Engine (qui ne stocke aucune métrique/métadonnée, par design).
    dataset_rows_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    company: Mapped["Company"] = relationship(back_populates="model_registries")
    training_job: Mapped["TrainingJob"] = relationship(back_populates="model_registries")
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="model_registry")
