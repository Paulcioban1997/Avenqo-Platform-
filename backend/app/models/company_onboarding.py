from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, OnboardingStatus, TimestampMixin


class CompanyOnboarding(TimestampMixin, Base):
    """Réponses au questionnaire d'onboarding, une ligne par entreprise.

    Créée paresseusement (`OnboardingService._get_or_create`) au premier
    accès plutôt qu'à l'inscription, pour ne jamais bloquer `AuthService.register`
    sur une préoccupation distincte.
    """

    __tablename__ = "company_onboarding"

    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[OnboardingStatus] = mapped_column(
        SAEnum(OnboardingStatus, name="onboarding_status"),
        default=OnboardingStatus.PENDING,
        nullable=False,
    )
    business_goals: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    current_tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    team_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    refined_industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship(back_populates="onboarding")
