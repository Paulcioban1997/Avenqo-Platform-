"""Persistance de facturation indÃ©pendante du catalogue des modules IA."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


class BillingAccount(TimestampMixin, Base):
    """Associe un tenant Avenqo Ã  son abonnement Stripe courant."""

    __tablename__ = "billing_accounts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False, default="demo")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="inactive")
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(nullable=False, default=False)

    company: Mapped["Company"] = relationship()


class BillingInvoice(Base):
    """Snapshot local d'une facture Stripe visible dans l'historique."""

    __tablename__ = "billing_invoices"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    stripe_invoice_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    plan_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    subtotal: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    discount_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tax_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    amount_due: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_paid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    line_items: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    billing_details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    tax_identifiers: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hosted_invoice_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    invoice_pdf: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AICreditPurchase(TimestampMixin, Base):
    """Achat de crédits créé côté serveur et rapproché avec Stripe."""

    __tablename__ = "ai_credit_purchases"
    __table_args__ = (
        CheckConstraint("credits_granted >= 0", name="ck_ai_credit_purchase_granted_nonnegative"),
        CheckConstraint("credits_remaining >= 0", name="ck_ai_credit_purchase_remaining_nonnegative"),
        CheckConstraint("credits_reserved >= 0", name="ck_ai_credit_purchase_reserved_nonnegative"),
        CheckConstraint("credits_reserved <= credits_remaining", name="ck_ai_credit_purchase_reserved_available"),
        CheckConstraint("price_usd_cents >= 0", name="ck_ai_credit_purchase_price_nonnegative"),
        CheckConstraint("refunded_amount >= 0", name="ck_ai_credit_purchase_refund_nonnegative"),
        CheckConstraint("credits_reversed >= 0", name="ck_ai_credit_purchase_reversed_nonnegative"),
        CheckConstraint("refund_shortfall_credits >= 0", name="ck_ai_credit_purchase_shortfall_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    stripe_customer_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    pack_code: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False)
    credits_granted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credits_reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_usd_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_paid: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="creating")
    refunded_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    credits_reversed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refund_shortfall_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    company: Mapped["Company"] = relationship()


class StripeWebhookEvent(Base):
    """MÃ©morise les Ã©vÃ©nements Stripe traitÃ©s pour garantir l'idempotence."""

    __tablename__ = "stripe_webhook_events"

    stripe_event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
