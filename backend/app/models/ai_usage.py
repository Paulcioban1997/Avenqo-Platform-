"""Suivi de l'usage IA par tenant, indépendant du fournisseur LLM.

Chaque ligne agrège l'usage d'un tenant pour une période de facturation
(mensuelle, ex. "2025-06") et un plan d'abonnement donné. Les compteurs sont
incrémentés après chaque appel IA réussi (message envoyé/streamé, tokens LLM
consommés, outils exécutés, prédictions générées) et jamais avant, afin de ne
refléter que l'usage réellement effectué.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


class TenantAIUsage(Base, TimestampMixin):
    """Compteurs d'usage IA Avenqo pour un tenant et une période donnée."""

    __tablename__ = "tenant_ai_usage"
    __table_args__ = (
        UniqueConstraint("company_id", "billing_period", name="uq_tenant_ai_usage_company_period"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    billing_period: Mapped[str] = mapped_column(String(7), nullable=False)  # "YYYY-MM"
    subscription_plan: Mapped[str] = mapped_column(String(100), nullable=False)

    ai_requests_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_tokens_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_calls_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    predictive_requests_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    company: Mapped["Company"] = relationship()


class TenantAICreditBalance(Base, TimestampMixin):
    """Crédits Avenqo du tenant; seul l'inclus suit le cycle mensuel."""

    __tablename__ = "tenant_ai_credit_balances"
    __table_args__ = (
        CheckConstraint("monthly_used >= 0", name="ck_ai_credit_monthly_used_nonnegative"),
        CheckConstraint("purchased_balance >= 0", name="ck_ai_credit_purchased_nonnegative"),
    )

    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        primary_key=True,
    )
    monthly_period: Mapped[str] = mapped_column(String(7), nullable=False)
    monthly_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purchased_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    company: Mapped["Company"] = relationship()
