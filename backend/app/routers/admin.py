"""Avenqo Admin Command Center (Phase 33) : routes réservées aux `platform_admin`.

Jamais accessible à un `tenant_admin` (owner/admin d'entreprise) : voir
`require_platform_admin`. Les données métier d'un tenant ne sont accessibles
qu'en lecture, via un contexte explicite validé et audité côté serveur.
"""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies.admin import (
    get_admin_service,
    get_admin_tenant_context,
    get_audit_log_service,
)
from backend.app.dependencies.auth import CurrentIdentity, require_platform_admin
from backend.app.dependencies.dashboard import get_tenant_dashboard_service
from backend.app.dependencies.tenant_business import (
    get_tenant_customers_service,
    get_tenant_products_service,
    get_tenant_recommendations_service,
    get_tenant_sales_service,
)
from backend.app.core.rate_limit import rate_limit
from backend.app.schemas.admin import (
    AuditLogEntryResponse,
    AdminTenantContextResponse,
    CompanyDetailResponse,
    CompanyDirectoryEntryResponse,
    DashboardResponse,
    SetEnterpriseOverrideRequest,
)
from backend.app.schemas.tenant_business import (
    CustomerListItemResponse,
    TenantCustomersResponse,
    TenantSalesResponse,
)
from backend.app.schemas.tenant_dashboard import TenantDashboardResponse
from backend.app.schemas.tenant_products_recommendations import (
    ProductDetailResponse,
    TenantProductsResponse,
    TenantRecommendationsResponse,
)
from backend.app.routers.dashboard import get_dashboard as get_tenant_dashboard
from backend.app.routers.tenant_business import (
    customer_detail as get_tenant_customer,
    customers_summary as get_tenant_customers,
    sales_summary as get_tenant_sales,
)
from backend.app.routers.tenant_products_recommendations import (
    product_detail as get_tenant_product,
    products_summary as get_tenant_products,
    recommendations as get_tenant_recommendations,
)
from backend.app.services.admin_service import AdminService
from backend.app.services.audit_log_service import AuditLogService
from backend.app.services.tenant_customers_service import TenantCustomersService
from backend.app.services.tenant_dashboard_service import TenantDashboardService
from backend.app.services.tenant_products_service import TenantProductsService
from backend.app.services.tenant_recommendations_service import TenantRecommendationsService
from backend.app.services.tenant_sales_service import TenantSalesService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(
    prefix="/admin",
    tags=["avenqo-admin"],
    dependencies=[
        Depends(require_platform_admin),
        Depends(rate_limit("admin", "rate_limit_admin_per_minute")),
    ],
)


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(service: AdminService = Depends(get_admin_service)) -> DashboardResponse:
    return DashboardResponse(**asdict(service.dashboard()))


@router.get("/companies", response_model=list[CompanyDirectoryEntryResponse])
def list_companies(
    service: AdminService = Depends(get_admin_service),
    skip: int = 0,
    limit: int = 50,
) -> list[CompanyDirectoryEntryResponse]:
    limit = min(max(limit, 1), 200)
    skip = max(skip, 0)
    entries = [CompanyDirectoryEntryResponse(**asdict(entry)) for entry in service.company_directory()]
    return entries[skip : skip + limit]


@router.get("/companies/{company_id}", response_model=CompanyDetailResponse)
def get_company(company_id: UUID, service: AdminService = Depends(get_admin_service)) -> CompanyDetailResponse:
    detail = service.company_detail(company_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return CompanyDetailResponse(**asdict(detail))


@router.post(
    "/companies/{company_id}/retail/context",
    response_model=AdminTenantContextResponse,
)
def enter_retail_tenant_context(
    company_id: UUID,
    tenant: TenantContext = Depends(get_admin_tenant_context),
    identity: CurrentIdentity = Depends(require_platform_admin),
    service: AdminService = Depends(get_admin_service),
    audit_log: AuditLogService = Depends(get_audit_log_service),
) -> AdminTenantContextResponse:
    detail = service.company_detail(tenant.company_id)
    assert detail is not None
    audit_log.record(
        actor_user_id=identity.user.id,
        action="admin_retail_context_entered",
        target_type="company",
        target_id=str(company_id),
        company_id=company_id,
    )
    return AdminTenantContextResponse(company_id=company_id, company_name=detail.name)


@router.post(
    "/companies/{company_id}/retail/context/exit",
    status_code=status.HTTP_204_NO_CONTENT,
)
def exit_retail_tenant_context(
    company_id: UUID,
    tenant: TenantContext = Depends(get_admin_tenant_context),
    identity: CurrentIdentity = Depends(require_platform_admin),
    audit_log: AuditLogService = Depends(get_audit_log_service),
) -> None:
    audit_log.record(
        actor_user_id=identity.user.id,
        action="admin_retail_context_exited",
        target_type="company",
        target_id=str(tenant.company_id),
        company_id=tenant.company_id,
    )


@router.get("/companies/{company_id}/retail/dashboard", response_model=TenantDashboardResponse)
def admin_retail_dashboard(
    tenant: TenantContext = Depends(get_admin_tenant_context),
    service: TenantDashboardService = Depends(get_tenant_dashboard_service),
) -> TenantDashboardResponse:
    return get_tenant_dashboard(tenant=tenant, service=service)


@router.get("/companies/{company_id}/retail/sales/summary", response_model=TenantSalesResponse)
def admin_retail_sales(
    period: str = "last_30_days",
    tenant: TenantContext = Depends(get_admin_tenant_context),
    service: TenantSalesService = Depends(get_tenant_sales_service),
) -> TenantSalesResponse:
    return get_tenant_sales(period=period, date_from=None, date_to=None, tenant=tenant, service=service)


@router.get("/companies/{company_id}/retail/customers/summary", response_model=TenantCustomersResponse)
def admin_retail_customers(
    page: int = 1,
    page_size: int = 25,
    search: str | None = None,
    tenant: TenantContext = Depends(get_admin_tenant_context),
    service: TenantCustomersService = Depends(get_tenant_customers_service),
) -> TenantCustomersResponse:
    return get_tenant_customers(
        page=page,
        page_size=page_size,
        search=search,
        segment=None,
        risk=None,
        sort_by="total_value",
        sort_direction="desc",
        tenant=tenant,
        service=service,
    )


@router.get("/companies/{company_id}/retail/customers/{customer_id}", response_model=CustomerListItemResponse)
def admin_retail_customer(
    customer_id: str,
    tenant: TenantContext = Depends(get_admin_tenant_context),
    service: TenantCustomersService = Depends(get_tenant_customers_service),
) -> CustomerListItemResponse:
    return get_tenant_customer(customer_id=customer_id, tenant=tenant, service=service)


@router.get("/companies/{company_id}/retail/products/summary", response_model=TenantProductsResponse)
def admin_retail_products(
    page: int = 1,
    page_size: int = 25,
    search: str | None = None,
    category: str | None = None,
    performance: str | None = None,
    sort_by: str = "revenue",
    sort_direction: str = "desc",
    tenant: TenantContext = Depends(get_admin_tenant_context),
    service: TenantProductsService = Depends(get_tenant_products_service),
) -> TenantProductsResponse:
    return get_tenant_products(
        page=page,
        page_size=page_size,
        search=search,
        category=category,
        performance=performance,
        status_filter=None,
        sort_by=sort_by,
        sort_direction=sort_direction,
        tenant=tenant,
        service=service,
    )


@router.get("/companies/{company_id}/retail/products/{product_id}", response_model=ProductDetailResponse)
def admin_retail_product(
    product_id: str,
    tenant: TenantContext = Depends(get_admin_tenant_context),
    service: TenantProductsService = Depends(get_tenant_products_service),
) -> ProductDetailResponse:
    return get_tenant_product(product_id=product_id, tenant=tenant, service=service)


@router.get(
    "/companies/{company_id}/retail/recommendations",
    response_model=TenantRecommendationsResponse,
)
def admin_retail_recommendations(
    tenant: TenantContext = Depends(get_admin_tenant_context),
    service: TenantRecommendationsService = Depends(get_tenant_recommendations_service),
) -> TenantRecommendationsResponse:
    return get_tenant_recommendations(tenant=tenant, service=service)


@router.put("/companies/{company_id}/enterprise-override", response_model=CompanyDetailResponse)
def set_enterprise_override(
    company_id: UUID,
    request: SetEnterpriseOverrideRequest,
    identity: CurrentIdentity = Depends(require_platform_admin),
    service: AdminService = Depends(get_admin_service),
) -> CompanyDetailResponse:
    try:
        service.set_enterprise_override(
            actor_user_id=identity.user.id,
            company_id=company_id,
            quota_overrides=request.quota_overrides,
            capability_overrides=request.capability_overrides,
            notes=request.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    detail = service.company_detail(company_id)
    assert detail is not None
    return CompanyDetailResponse(**asdict(detail))


@router.get("/audit-log", response_model=list[AuditLogEntryResponse])
def get_audit_log(
    audit_log: AuditLogService = Depends(get_audit_log_service),
    limit: int = 100,
) -> list[AuditLogEntryResponse]:
    limit = min(max(limit, 1), 500)
    return [
        AuditLogEntryResponse(
            id=entry.id,
            actor_user_id=entry.actor_user_id,
            action=entry.action,
            target_type=entry.target_type,
            target_id=entry.target_id,
            company_id=entry.company_id,
            safe_metadata=entry.safe_metadata,
            created_at=entry.created_at,
        )
        for entry in audit_log.recent(limit=limit)
    ]
