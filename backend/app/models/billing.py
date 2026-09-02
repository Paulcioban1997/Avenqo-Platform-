"""Persistance de facturation indÃ©pendante du catalogue des modules IA."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
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
    number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    plan_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    amount_due: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_paid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hosted_invoice_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    invoice_pdf: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StripeWebhookEvent(Base):
    """MÃ©morise les Ã©vÃ©nements Stripe traitÃ©s pour garantir l'idempotence."""

    __tablename__ = "stripe_webhook_events"

    stripe_event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
