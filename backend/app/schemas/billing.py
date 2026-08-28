"""Schémas HTTP de la facturation Avenqo."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PlanResponse(BaseModel):
    code: str
    name: str
    requires_sales_contact: bool
    monthly_price_usd: int | None
    included_ai_credits: int | None


class AICreditPackResponse(BaseModel):
    code: str
    credits: int
    price_usd: int


class AICreditBalanceResponse(BaseModel):
    billing_period: str
    monthly_allowance: int
    monthly_remaining: int
    purchased_remaining: int
    total_remaining: int


class CheckoutRequest(BaseModel):
    plan_code: str = Field(min_length=2, max_length=64)


class CreditCheckoutRequest(BaseModel):
    pack_code: str = Field(min_length=2, max_length=64)


class ChangePlanRequest(CheckoutRequest):
    pass


class RedirectResponse(BaseModel):
    url: str


class SubscriptionResponse(BaseModel):
    plan_code: str
    status: str
    current_period_end: datetime | None
    cancel_at_period_end: bool


class InvoiceResponse(BaseModel):
    id: UUID
    number: str | None
    status: str
    currency: str
    amount_due: int
    amount_paid: int
    hosted_invoice_url: str | None
    invoice_pdf: str | None
    issued_at: datetime

    model_config = {"from_attributes": True}
