import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.tenant_business import (
    get_tenant_products_service,
    get_tenant_recommendations_service,
)
from backend.app.schemas.tenant_products_recommendations import (
    ProductDetailResponse,
    TenantProductsResponse,
    TenantRecommendationsResponse,
)
from backend.app.services.tenant_products_service import (
    InvalidProductQuery,
    ProductNotFound,
    TenantProductsService,
)
from backend.app.services.tenant_recommendations_service import TenantRecommendationsService
from shared.ai_engine.contracts import TenantContext


logger = logging.getLogger(__name__)
products_router = APIRouter(prefix="/products", tags=["products"])
recommendations_router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@products_router.get("/summary", response_model=TenantProductsResponse)
def products_summary(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    search: str | None = Query(default=None, max_length=120),
    category: str | None = Query(default=None, max_length=120),
    performance: str | None = Query(default=None, max_length=40),
    status_filter: str | None = Query(default=None, alias="status", max_length=40),
    sort_by: str = Query(default="revenue"),
    sort_direction: str = Query(default="desc"),
    tenant: TenantContext = Depends(get_tenant_context),
    service: TenantProductsService = Depends(get_tenant_products_service),
) -> TenantProductsResponse:
    try:
        return TenantProductsResponse.model_validate(
            service.build(
                tenant,
                page=page,
                page_size=page_size,
                search=search,
                category=category,
                performance=performance,
                status=status_filter,
                sort_by=sort_by,
                sort_direction=sort_direction,
            )
        )
    except InvalidProductQuery as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Tenant product generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Product analytics temporarily unavailable",
        ) from exc


@products_router.get("/{product_id}", response_model=ProductDetailResponse)
def product_detail(
    product_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    service: TenantProductsService = Depends(get_tenant_products_service),
) -> ProductDetailResponse:
    try:
        return ProductDetailResponse.model_validate(service.get_product(tenant, product_id))
    except ProductNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found") from exc
    except Exception as exc:
        logger.exception("Tenant product lookup failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Product temporarily unavailable",
        ) from exc


@recommendations_router.get("", response_model=TenantRecommendationsResponse)
def recommendations(
    tenant: TenantContext = Depends(get_tenant_context),
    service: TenantRecommendationsService = Depends(get_tenant_recommendations_service),
) -> TenantRecommendationsResponse:
    try:
        return TenantRecommendationsResponse.model_validate(service.build(tenant))
    except Exception as exc:
        logger.exception("Tenant recommendation generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Recommendations temporarily unavailable",
        ) from exc