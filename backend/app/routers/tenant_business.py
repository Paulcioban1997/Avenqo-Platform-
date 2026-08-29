import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.tenant_business import (
    get_tenant_customers_service,
    get_tenant_sales_service,
)
from backend.app.schemas.tenant_business import (
    CustomerListItemResponse,
    TenantCustomersResponse,
    TenantSalesResponse,
)
from backend.app.services.tenant_customers_service import (
    CustomerNotFound,
    InvalidCustomerQuery,
    TenantCustomersService,
)
from backend.app.services.tenant_sales_service import InvalidSalesPeriod, TenantSalesService
from shared.ai_engine.contracts import TenantContext


logger = logging.getLogger(__name__)
sales_router = APIRouter(prefix="/sales", tags=["sales"])
customers_router = APIRouter(prefix="/customers", tags=["customers"])


@sales_router.get("/summary", response_model=TenantSalesResponse)
def sales_summary(
    period: str = Query(default="last_30_days"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    tenant: TenantContext = Depends(get_tenant_context),
    service: TenantSalesService = Depends(get_tenant_sales_service),
) -> TenantSalesResponse:
    try:
        return TenantSalesResponse.model_validate(
            service.build(tenant, period_key=period, date_from=date_from, date_to=date_to)
        )
    except InvalidSalesPeriod as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Tenant sales generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sales analytics temporarily unavailable",
        ) from exc


@customers_router.get("/summary", response_model=TenantCustomersResponse)
def customers_summary(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    search: str | None = Query(default=None, max_length=120),
    segment: str | None = Query(default=None, max_length=120),
    risk: str | None = Query(default=None, max_length=120),
    sort_by: str = Query(default="total_value"),
    sort_direction: str = Query(default="desc"),
    tenant: TenantContext = Depends(get_tenant_context),
    service: TenantCustomersService = Depends(get_tenant_customers_service),
) -> TenantCustomersResponse:
    try:
        return TenantCustomersResponse.model_validate(
            service.build(
                tenant,
                page=page,
                page_size=page_size,
                search=search,
                segment=segment,
                risk=risk,
                sort_by=sort_by,
                sort_direction=sort_direction,
            )
        )
    except InvalidCustomerQuery as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Tenant customers generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Customer analytics temporarily unavailable",
        ) from exc


@customers_router.get("/{customer_id}", response_model=CustomerListItemResponse)
def customer_detail(
    customer_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    service: TenantCustomersService = Depends(get_tenant_customers_service),
) -> CustomerListItemResponse:
    try:
        return CustomerListItemResponse.model_validate(service.get_customer(tenant, customer_id))
    except CustomerNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found") from exc
    except Exception as exc:
        logger.exception("Tenant customer lookup failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Customer temporarily unavailable",
        ) from exc