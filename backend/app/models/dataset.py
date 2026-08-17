from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, DatasetStatus


class Dataset(Base):
    """Représente un jeu de données importé appartenant à une entreprise."""

    __tablename__ = "datasets"

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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    rows_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    columns_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[DatasetStatus] = mapped_column(
        SAEnum(DatasetStatus, name="dataset_status"),
        nullable=False,
        default=DatasetStatus.UPLOADED,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    company: Mapped["Company"] = relationship(back_populates="datasets")
    mapping: Mapped["Mapping | None"] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        uselist=False,
    )
    quality_report: Mapped["DataQualityReport | None"] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        uselist=False,
    )
    profile: Mapped["DatasetProfile | None"] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        uselist=False,
    )
    versions: Mapped[list["DatasetVersion"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
    )
    training_jobs: Mapped[list["TrainingJob"]] = relationship(back_populates="dataset")
