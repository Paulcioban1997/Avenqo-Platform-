"""SchÃ©mas HTTP de la facturation Avenqo."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PlanResponse(BaseModel):
    code: str
    name: str
    requires_sales_contact: bool
    monthly_price_usd: int | None


class CheckoutRequest(BaseModel):
    plan_code: str = Field(min_length=2, max_length=64)


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
