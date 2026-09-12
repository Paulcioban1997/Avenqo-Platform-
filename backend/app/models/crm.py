"""Modèles de données canoniques pour le module CRM AI (Phase 13)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class CRMLead(TimestampMixin, Base):
    """Prospect qualifié ou entrant géré par le module CRM AI."""

    __tablename__ = "crm_leads"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(150), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="website")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="new", index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)  # 0 à 100
    estimated_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    conversion_probability: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    next_step: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class CRMOpportunity(TimestampMixin, Base):
    """Opportunité commerciale du pipeline CRM AI."""

    __tablename__ = "crm_opportunities"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    lead_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_leads.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="CAD")
    stage: Mapped[str] = mapped_column(String(50), nullable=False, default="discovery", index=True)
    probability: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    expected_close_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CRMActivity(TimestampMixin, Base):
    """Interaction, tâche ou recommandation d'action CRM."""

    __tablename__ = "crm_activities"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lead_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crm_leads.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False, default="task")
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    priority: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class CRMContact(TimestampMixin, Base):
    """Client / Contact avec métriques d'engagement, CLV et risque de churn."""

    __tablename__ = "crm_contacts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_lifetime_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    churn_risk: Mapped[str] = mapped_column(String(50), nullable=False, default="low", index=True)
    churn_risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.1)
    churn_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
