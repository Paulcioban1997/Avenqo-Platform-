"""Suivi de l'usage IA par tenant, indépendant du fournisseur LLM.

Chaque ligne agrège l'usage d'un tenant pour une période de facturation
(mensuelle, ex. "2025-06") et un plan d'abonnement donné. Les compteurs sont
incrémentés après chaque appel IA réussi (message envoyé/streamé, tokens LLM
consommés, outils exécutés, prédictions générées) et jamais avant, afin de ne
refléter que l'usage réellement effectué.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
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
    """Allocation incluse et crédits achetés persistants d'un tenant."""

    __tablename__ = "tenant_ai_credit_balances"
    __table_args__ = (
        CheckConstraint("monthly_used >= 0", name="ck_ai_credit_monthly_used_nonnegative"),
        CheckConstraint("purchased_balance >= 0", name="ck_ai_credit_purchased_nonnegative"),
        CheckConstraint("included_reserved >= 0", name="ck_ai_credit_included_reserved_nonnegative"),
        CheckConstraint("purchased_reserved >= 0", name="ck_ai_credit_purchased_reserved_nonnegative"),
        CheckConstraint("purchased_reserved <= purchased_balance", name="ck_ai_credit_purchased_reserved_available"),
    )

    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        primary_key=True,
    )
    monthly_period: Mapped[str] = mapped_column(String(7), nullable=False)
    monthly_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purchased_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    included_reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purchased_reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    company: Mapped["Company"] = relationship()


class TenantAICreditReservation(Base):
    """Réservation atomique de crédits pour une requête IA tenant-scopée."""

    __tablename__ = "tenant_ai_credit_reservations"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "avenqo_request_id",
            name="uq_ai_credit_reservation_company_request",
        ),
        CheckConstraint("estimated_credits > 0", name="ck_ai_credit_reservation_estimate_positive"),
        CheckConstraint("reserved_included >= 0", name="ck_ai_credit_reservation_included_nonnegative"),
        CheckConstraint("reserved_purchased >= 0", name="ck_ai_credit_reservation_purchased_nonnegative"),
        CheckConstraint("actual_credits >= 0", name="ck_ai_credit_reservation_actual_nonnegative"),
        CheckConstraint("settled_included >= 0", name="ck_ai_credit_reservation_settled_included_nonnegative"),
        CheckConstraint("settled_purchased >= 0", name="ck_ai_credit_reservation_settled_purchased_nonnegative"),
        CheckConstraint("unfunded_credits >= 0", name="ck_ai_credit_reservation_unfunded_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    avenqo_request_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    billing_period: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="reserved")
    estimated_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_purchased: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actual_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    settled_included: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    settled_purchased: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unfunded_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purchase_allocations: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship()


class TenantAICreditLedgerEntry(Base):
    """Mouvement immuable du portefeuille IA d'un tenant."""

    __tablename__ = "tenant_ai_credit_ledger"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    billing_period: Mapped[str] = mapped_column(String(7), nullable=False)
    included_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purchased_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    included_reserved_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purchased_reserved_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monthly_used_after: Mapped[int] = mapped_column(Integer, nullable=False)
    purchased_balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    included_reserved_after: Mapped[int] = mapped_column(Integer, nullable=False)
    purchased_reserved_after: Mapped[int] = mapped_column(Integer, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    company: Mapped["Company"] = relationship()


class TenantAIProviderAttempt(Base):
    """Immutable provider-cost snapshot for one tenant-scoped LLM attempt."""

    __tablename__ = "tenant_ai_provider_attempts"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "avenqo_request_id",
            "attempt_number",
            name="uq_ai_provider_attempt_company_request_number",
        ),
        CheckConstraint("attempt_number > 0", name="ck_ai_provider_attempt_number_positive"),
        CheckConstraint("provider_cost_usd >= 0", name="ck_ai_provider_attempt_cost_nonnegative"),
        CheckConstraint("avenqo_credits >= 0", name="ck_ai_provider_attempt_credits_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    avenqo_request_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operation: Mapped[str] = mapped_column(String(50), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_cost_usd: Mapped[Decimal] = mapped_column(Numeric(20, 12), nullable=False)
    input_cost_per_million_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    cached_input_cost_per_million_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    output_cost_per_million_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    tool_call_cost_usd: Mapped[Decimal] = mapped_column(Numeric(20, 12), nullable=False)
    avenqo_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    company: Mapped["Company"] = relationship()
