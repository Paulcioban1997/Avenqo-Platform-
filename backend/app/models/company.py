from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Enum as SAEnum, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, CompanyStatus, TimestampMixin


class Company(TimestampMixin, Base):
    """Représente l'entreprise locataire propriétaire de ses ressources."""

    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    billing_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    industry: Mapped[str] = mapped_column(String(120), nullable=False)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str] = mapped_column(String(100), nullable=False, default="North America")
    company_size: Mapped[str] = mapped_column(String(50), nullable=False, default="1-10")
    preferred_language: Mapped[str] = mapped_column(String(10), nullable=False, default="fr")
    subscription_plan: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[CompanyStatus] = mapped_column(
        SAEnum(CompanyStatus, name="company_status"),
        default=CompanyStatus.ACTIVE,
        nullable=False,
    )

    users: Mapped[list["User"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    datasets: Mapped[list["Dataset"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    company_modules: Mapped[list["CompanyModule"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    ai_jobs: Mapped[list["AIJob"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    training_jobs: Mapped[list["TrainingJob"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    model_registries: Mapped[list["ModelRegistry"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    predictions: Mapped[list["Prediction"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )
    onboarding: Mapped["CompanyOnboarding | None"] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        uselist=False,
    )
