"""Durable consent, payment and telecom provisioning state; no provider secrets."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.models.base import Base, TimestampMixin


class VoiceNumberTariff(TimestampMixin, Base):
    __tablename__ = "voice_number_tariffs"
    __table_args__ = (UniqueConstraint("country", "number_type", "currency", name="uq_voice_tariff_market"), CheckConstraint("monthly_amount > 0", name="ck_voice_tariff_amount"))
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    number_type: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    monthly_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    stripe_price_id: Mapped[str | None] = mapped_column(String(255))
    provider_cost_limits: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class VoiceProvisioningOrder(TimestampMixin, Base):
    __tablename__ = "voice_provisioning_orders"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id"), index=True, nullable=False)
    actor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="QUOTED", index=True)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stripe_customer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    stripe_subscription_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    stripe_invoice_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    stripe_item_id: Mapped[str | None] = mapped_column(String(255))
    invoice_url: Mapped[str | None] = mapped_column(String(2048))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_order_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    provider_number_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    number_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("voice_phone_numbers.id"))
    config_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("voice_business_configs.id"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    suspended_by_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class VoiceProvisioningClaim(Base):
    __tablename__ = "voice_provisioning_claims"
    phone_number: Mapped[str] = mapped_column(String(32), primary_key=True)
    order_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("voice_provisioning_orders.id"), unique=True, nullable=False)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id"), unique=True, nullable=False)

class VoiceTelecomCost(Base):
    __tablename__="voice_telecom_costs"
    call_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),ForeignKey("voice_calls.id"),primary_key=True)
    company_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),ForeignKey("companies.id"),nullable=False,index=True)
    event_id:Mapped[str]=mapped_column(String(255),nullable=False,unique=True)
    occurred_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    status:Mapped[str]=mapped_column(String(32),nullable=False)
    costs_by_currency:Mapped[dict]=mapped_column(JSON,nullable=False)
    billed_seconds:Mapped[int]=mapped_column(Integer,nullable=False,default=0)
