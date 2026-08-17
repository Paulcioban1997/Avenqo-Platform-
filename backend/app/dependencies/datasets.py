"""Dépendances FastAPI de l'import de datasets."""

from pathlib import Path

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.database import get_db
from backend.app.repositories import SQLAlchemyModuleEntitlements
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from backend.app.services.dataset_import_service import DatasetImportService
from modules.entitlements import ModuleAccessService
from shared.ai_engine.dataset_ingestion.storage import LocalDatasetStorage


def get_dataset_import_service(db: Session = Depends(get_db)) -> DatasetImportService:
    settings = get_settings()
    return DatasetImportService(
        session=db,
        artifacts=ArtifactService(Path(settings.artifact_root)),
        access=ModuleAccessService(SQLAlchemyModuleEntitlements(db)),
        max_upload_bytes=settings.dataset_max_upload_mb * 1024 * 1024,
    )


def get_company_dataset_ingestion_service(
    db: Session = Depends(get_db),
) -> CompanyDatasetIngestionService:
    settings = get_settings()
    return CompanyDatasetIngestionService(
        session=db,
        storage=LocalDatasetStorage(Path(settings.artifact_root) / "company_datasets"),
        access=ModuleAccessService(SQLAlchemyModuleEntitlements(db)),
        max_upload_bytes=settings.dataset_max_upload_mb * 1024 * 1024,
    )