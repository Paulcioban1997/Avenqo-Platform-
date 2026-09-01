from fastapi import Depends
from backend.app.dependencies.tenant_business import (
    get_tenant_analytics_service,
    get_tenant_recommendations_service,
)
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from backend.app.services.tenant_dashboard_service import TenantDashboardService
from backend.app.services.tenant_recommendations_service import TenantRecommendationsService


def get_tenant_dashboard_service(
    analytics: TenantAnalyticsService = Depends(get_tenant_analytics_service),
    recommendations: TenantRecommendationsService = Depends(get_tenant_recommendations_service),
) -> TenantDashboardService:
    return TenantDashboardService(analytics, recommendations)