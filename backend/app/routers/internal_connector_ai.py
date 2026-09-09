"""Protected infrastructure trigger for connector AI evaluations."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import sessionmaker

from backend.app.config.settings import get_settings
from backend.app.database.session import get_session_factory
from backend.app.dependencies.training import get_training_dispatcher
from backend.app.services.connector_ai_evaluation_service import (
    ConnectorAIEvaluationService,
)
from backend.app.services.training_dispatcher import TrainingDispatcher

router = APIRouter(tags=["internal-connector-ai"])


@router.post("/connector-ai/evaluate")
def evaluate_connector_changes(
    x_avenqo_scheduler_token: str = Header(default=""),
    session_factory: sessionmaker = Depends(get_session_factory),
    dispatcher: TrainingDispatcher = Depends(get_training_dispatcher),
) -> dict[str, int]:
    settings = get_settings()
    configured_token = settings.connector_ai_scheduler_token
    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Connector AI scheduler is not configured",
        )
    if not secrets.compare_digest(x_avenqo_scheduler_token, configured_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid scheduler credentials",
        )
    processed = ConnectorAIEvaluationService(
        session_factory,
        dispatcher,
        lease_seconds=settings.connector_ai_evaluation_lease_seconds,
        batch_size=settings.connector_ai_evaluation_batch_size,
    ).run_due()
    return {"claimed": processed}