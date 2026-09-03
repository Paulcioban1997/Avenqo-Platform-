"""Dépendances FastAPI de l'import de datasets."""

from pathlib import Path

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.database import get_db
from backend.app.dependencies.training import get_training_dispatcher
from backend.app.dependencies.ai_engine import get_ai_model_registry
from backend.app.repositories import SQLAlchemyModuleEntitlements
from backend.app.services.artifact_service import ArtifactService
from backend.app.services.automatic_company_dataset_ingestion_service import (
    AutomaticCompanyDatasetIngestionService,
)
from backend.app.services.capability_execution_gate import CapabilityExecutionGate
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from backend.app.services.data_import_policy import DataImportPolicy
from backend.app.services.dataset_cleaning_service import DatasetCleaningService
from backend.app.services.dataset_import_service import DatasetImportService
from backend.app.services.training_dispatcher import TrainingDispatcher
from modules.entitlements import ModuleAccessService
from shared.ai_engine.dataset_ingestion.storage import LocalDatasetStorage
from shared.ai_engine.registry.registry import ModelRegistry


def get_data_import_policy(db: Session = Depends(get_db)) -> DataImportPolicy:
    return DataImportPolicy(db)


def get_dataset_import_service(
    db: Session = Depends(get_db),
    quota: DataImportPolicy = Depends(get_data_import_policy),
    model_registry: ModelRegistry = Depends(get_ai_model_registry),
) -> DatasetImportService:
    settings = get_settings()
    return DatasetImportService(
        session=db,
        artifacts=ArtifactService(Path(settings.artifact_root)),
        quota=quota,
        max_upload_bytes=settings.dataset_max_upload_mb * 1024 * 1024,
        model_registry=model_registry,
    )


def get_company_dataset_ingestion_service(
    db: Session = Depends(get_db),
    quota: DataImportPolicy = Depends(get_data_import_policy),
    dispatcher: TrainingDispatcher = Depends(get_training_dispatcher),
) -> CompanyDatasetIngestionService:
    settings = get_settings()
    return AutomaticCompanyDatasetIngestionService(
        session=db,
        storage=LocalDatasetStorage(Path(settings.artifact_root) / "company_datasets"),
        quota=quota,
        max_upload_bytes=settings.dataset_max_upload_mb * 1024 * 1024,
        dispatcher=dispatcher,
    )


def get_capability_execution_gate(
    db: Session = Depends(get_db),
    service: CompanyDatasetIngestionService = Depends(get_company_dataset_ingestion_service),
) -> CapabilityExecutionGate:
    return CapabilityExecutionGate(
        service,
        access=ModuleAccessService(SQLAlchemyModuleEntitlements(db)),
    )


def get_dataset_cleaning_service(
    service: CompanyDatasetIngestionService = Depends(get_company_dataset_ingestion_service),
) -> DatasetCleaningService:
    return DatasetCleaningService(service)
