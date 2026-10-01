"""Dependency provider for the registered business AI tool catalog."""

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.ai.tools.business.registry_factory import build_business_tool_registry
from backend.app.ai.tools.registry import ToolRegistry
from backend.app.database import get_db
from backend.app.dependencies.ai_engine import get_prediction_service
from backend.app.dependencies.datasets import get_company_dataset_ingestion_service
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from shared.ai_engine.prediction.service import PredictionService


def get_business_tool_registry(
    db: Session = Depends(get_db),
    ingestion: CompanyDatasetIngestionService = Depends(get_company_dataset_ingestion_service),
    prediction_service: PredictionService = Depends(get_prediction_service),
) -> ToolRegistry:
    return build_business_tool_registry(db, ingestion, prediction_service)
