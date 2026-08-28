from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.datasets import get_company_dataset_ingestion_service
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from backend.app.services.tenant_dashboard_service import TenantDashboardService


def get_tenant_dashboard_service(
    db: Session = Depends(get_db),
    ingestion: CompanyDatasetIngestionService = Depends(get_company_dataset_ingestion_service),
) -> TenantDashboardService:
    return TenantDashboardService(db, ingestion)