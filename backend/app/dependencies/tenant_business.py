from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.ai_engine import get_prediction_service
from backend.app.dependencies.datasets import get_company_dataset_ingestion_service
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from backend.app.services.tenant_customers_service import TenantCustomersService
from backend.app.services.tenant_sales_service import TenantSalesService
from shared.ai_engine.prediction.service import PredictionService


def get_tenant_analytics_service(
    db: Session = Depends(get_db),
    ingestion: CompanyDatasetIngestionService = Depends(get_company_dataset_ingestion_service),
) -> TenantAnalyticsService:
    return TenantAnalyticsService(db, ingestion)


def get_tenant_sales_service(
    db: Session = Depends(get_db),
    analytics: TenantAnalyticsService = Depends(get_tenant_analytics_service),
    prediction_service: PredictionService = Depends(get_prediction_service),
) -> TenantSalesService:
    return TenantSalesService(db, analytics, prediction_service)


def get_tenant_customers_service(
    analytics: TenantAnalyticsService = Depends(get_tenant_analytics_service),
    prediction_service: PredictionService = Depends(get_prediction_service),
) -> TenantCustomersService:
    return TenantCustomersService(analytics, prediction_service)