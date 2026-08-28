"""Solde et registre immuable des crédits IA Avenqo par tenant."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


class AICreditBalance(Base, TimestampMixin):
    __tablename__ = "ai_credit_balances"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    billing_period: Mapped[str] = mapped_column(String(7), nullable=False)
    monthly_allowance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    monthly_remaining: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    purchased_remaining: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    company: Mapped["Company"] = relationship()

    @property
    def total_remaining(self) -> int:
        return int(self.monthly_remaining + self.purchased_remaining)


class AICreditTransaction(Base, TimestampMixin):
    __tablename__ = "ai_credit_transactions"
    __table_args__ = (
        UniqueConstraint("reference_id", name="uq_ai_credit_transactions_reference_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    transaction_type: Mapped[str] = mapped_column(String(40), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    company: Mapped["Company"] = relationship()
