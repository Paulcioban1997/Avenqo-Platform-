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


class CreditPackResponse(BaseModel):
    code: str
    credits: int
    price_usd: int


class CreditPackCheckoutRequest(BaseModel):
    pack_code: str = Field(min_length=1, max_length=64)


class AICreditBalanceResponse(BaseModel):
    billing_period: str
    billing_period_start: datetime
    billing_period_end: datetime
    monthly_allocation: int | None
    monthly_included: int | None
    monthly_used: int
    monthly_remaining: int | None
    purchased_total_available: int
    purchased_remaining: int
    total_available: int | None
    total_remaining: int | None


class PaymentMethodSummary(BaseModel):
    brand: str | None = "visa"
    last4: str | None = "4242"
    exp_month: int | None = 9
    exp_year: int | None = 2028


class SubscriptionResponse(BaseModel):
    plan_code: str
    status: str
    current_period_end: datetime | None
    cancel_at_period_end: bool
    plan_name: str | None = None
    monthly_price_usd: int | None = None
    billing_frequency: str | None = "monthly"
    currency: str | None = "USD"
    company_name: str | None = None
    payment_method: PaymentMethodSummary | None = None


class AICreditBreakdownItem(BaseModel):
    module: str
    credits_used: int
    percentage: float = 0.0


class AICreditBreakdownResponse(BaseModel):
    period: str
    total_used: int
    items: list[AICreditBreakdownItem]


class AICreditHistoryItem(BaseModel):
    id: str
    date: str
    module: str
    operation: str
    credits_used: int
    user: str = "Système"


class AICreditHistoryResponse(BaseModel):
    items: list[AICreditHistoryItem]
    total: int
    offset: int
    limit: int


class InvoiceResponse(BaseModel):
    id: UUID
    stripe_invoice_id: str
    stripe_subscription_id: str | None
    stripe_customer_id: str | None
    number: str | None
    plan_code: str | None
    status: str
    currency: str
    subtotal: int
    discount_total: int
    tax_total: int
    total: int
    amount_due: int
    amount_paid: int
    line_items: list[dict]
    billing_details: dict
    tax_identifiers: list[dict]
    hosted_invoice_url: str | None
    invoice_pdf: str | None
    period_start: datetime | None
    period_end: datetime | None
    issued_at: datetime
    paid_at: datetime | None
    due_at: datetime | None

    model_config = {"from_attributes": True}


class InvoiceHistoryResponse(BaseModel):
    items: list[InvoiceResponse]
    total: int
    offset: int
    limit: int


class InvoiceFiscalSummaryResponse(BaseModel):
    fiscal_year: int
    invoices_paid: int
    totals_by_currency: list[dict]
    missing_or_unpaid_invoices: int


class AdminInvoiceSummaryResponse(BaseModel):
    company_id: UUID
    company_name: str
    plan_code: str
    invoice_count: int
    latest_invoice: dict | None
    fiscal_totals: InvoiceFiscalSummaryResponse
