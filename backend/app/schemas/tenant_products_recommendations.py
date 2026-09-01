from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from backend.app.schemas.tenant_business import PaginationResponse, SalesTrendResponse


class ProductSummaryResponse(BaseModel):
    total_products: int
    active_products: int | None
    products_with_activity: int
    revenue: float | None
    units: float | None
    average_selling_price: float | None
    top_product_revenue_share: float | None
    out_of_stock_products: int | None


class ProductCategoryResponse(BaseModel):
    category: str
    product_count: int
    revenue: float | None
    units: float | None
    revenue_share: float | None


class ProductListItemResponse(BaseModel):
    product_id: str
    name: str | None
    category: str | None
    revenue: float | None
    current_revenue: float | None
    previous_revenue: float | None
    change_percent: float | None
    quantity: float | None
    orders: int
    average_price: float | None
    customer_reach: int | None
    last_activity: datetime | None
    stock_level: float | None
    performance: str | None
    status: str | None


class TenantProductsResponse(BaseModel):
    status: str
    available: bool
    currency: str
    capabilities: list[str]
    summary: ProductSummaryResponse | None
    categories: list[ProductCategoryResponse]
    trend: SalesTrendResponse
    items: list[ProductListItemResponse]
    pagination: PaginationResponse


class ProductDetailResponse(ProductListItemResponse):
    currency: str
    trend: SalesTrendResponse


class RecommendationResponse(BaseModel):
    id: str
    type: str
    title: str
    explanation: str
    priority: str
    source_capability: str
    evidence: dict[str, Any]
    affected_entity: str | None
    confidence: float | None
    estimated_impact: float | None
    suggested_action: str
    action_route: str | None
    generated_at: datetime
    source_model_version: str | None
    lifecycle: str


class TenantRecommendationsResponse(BaseModel):
    status: str
    currency: str
    generated_at: datetime
    recommendations: list[RecommendationResponse]