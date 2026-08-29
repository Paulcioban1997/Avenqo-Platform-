from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AnalyticsPeriodResponse(BaseModel):
    key: str
    start: datetime | None
    end: datetime | None
    comparison_start: datetime | None
    comparison_end: datetime | None
    date_filter_available: bool
    granularity: str


class SalesSummaryResponse(BaseModel):
    revenue: float
    orders: int
    average_order_value: float
    rows_considered: int
    previous_revenue: float | None
    previous_orders: int | None
    revenue_change_percent: float | None
    orders_change_percent: float | None


class SalesTrendPointResponse(BaseModel):
    period: str
    revenue: float
    orders: int


class SalesTrendResponse(BaseModel):
    granularity: str
    points: list[SalesTrendPointResponse]


class SalesForecastPointResponse(BaseModel):
    period: str
    value: float


class SalesForecastResponse(BaseModel):
    granularity: str
    forecasted_total: float
    points: list[SalesForecastPointResponse]


class TenantSalesResponse(BaseModel):
    status: str
    available: bool
    currency: str
    capabilities: list[str]
    period: AnalyticsPeriodResponse
    summary: SalesSummaryResponse | None
    trend: SalesTrendResponse
    strongest_period: SalesTrendPointResponse | None
    weakest_period: SalesTrendPointResponse | None
    forecast: SalesForecastResponse | None


class CustomerSummaryResponse(BaseModel):
    total_customers: int
    active_customers: int | None
    new_customers: int | None
    repeat_customers: int
    purchase_frequency: float
    average_customer_value: float | None


class CustomerGroupResponse(BaseModel):
    label: str
    count: int


class CustomerListItemResponse(BaseModel):
    customer_id: str
    orders: int
    total_value: float
    first_purchase: datetime | None
    last_purchase: datetime | None
    status: str | None
    segment: str | None
    risk: str | None


class PaginationResponse(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class TenantCustomersResponse(BaseModel):
    status: str
    available: bool
    currency: str
    capabilities: list[str]
    summary: CustomerSummaryResponse | None
    segments: list[CustomerGroupResponse]
    risks: list[CustomerGroupResponse]
    items: list[CustomerListItemResponse]
    pagination: PaginationResponse