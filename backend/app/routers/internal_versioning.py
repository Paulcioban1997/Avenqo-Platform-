"""Endpoint interne â€” Model Versioning Enterprise (Phase 9).

Comme `internal_retraining.py` (Phase 8), ce routeur n'est jamais consommÃ©
par le frontend Avenqo : aucun terme technique (version, rollback, UUID,
ModelRegistry, drift, XAI, hyperparameter search...) n'y transite jamais
vers l'utilisateur final â€” ces endpoints servent uniquement l'outillage
d'exploitation/admin interne.

Chaque version est crÃ©Ã©e automatiquement par `TrainingDispatcher` (voir
`_record_version`) â€” cet endpoint ne fait qu'exposer en LECTURE ce qui a
dÃ©jÃ  Ã©tÃ© enregistrÃ©, plus une action de rollback qui ne fait que changer la
version active (jamais de rÃ©entraÃ®nement).

MontÃ© Ã  part de `api_router` (prÃ©fixe `/internal`, jamais `/api/v1`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies.ai_engine import get_ai_model_registry
from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.training import get_training_dispatcher
from backend.app.schemas.training import (
    ModelVersionCompareRequest,
    ModelVersionCompareResponse,
    ModelVersionListResponse,
    ModelVersionRollbackRequest,
    ModelVersionRollbackResponse,
    ModelVersionSummaryResponse,
)
from backend.app.services.training_dispatcher import TrainingDispatcher
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.exceptions import ModelNotFoundError
from shared.ai_engine.registry.registry import ModelRegistry as AIModelRegistry
from shared.ai_engine.versioning.service import compare as compare_versions
from shared.ai_engine.versioning.service import list_versions as list_model_versions

router = APIRouter(tags=["internal-versioning"])


@router.get("/versioning/versions", response_model=ModelVersionListResponse)
def list_versions(
    module_code: str,
    task_code: str,
    tenant: TenantContext = Depends(get_tenant_context),
    ai_model_registry: AIModelRegistry = Depends(get_ai_model_registry),
) -> ModelVersionListResponse:
    summaries = list_model_versions(ai_model_registry, tenant, module_code, task_code)
    return ModelVersionListResponse(
        versions=[
            ModelVersionSummaryResponse(
                version=summary.version,
                version_number=summary.version_number,
                parent_version=summary.parent_version,
                model_name=summary.model_name,
                is_active=summary.is_active,
                state=summary.state,
                retraining_reason=summary.retraining_reason,
                created_at=summary.created_at,
            )
            for summary in summaries
        ]
    )


@router.post("/versioning/compare", response_model=ModelVersionCompareResponse)
def compare_two_versions(
    request: ModelVersionCompareRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    ai_model_registry: AIModelRegistry = Depends(get_ai_model_registry),
) -> ModelVersionCompareResponse:
    try:
        result = compare_versions(
            ai_model_registry,
            tenant,
            request.module_code,
            request.task_code,
            request.version_a,
            request.version_b,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found") from exc

    return ModelVersionCompareResponse(
        version_a=result.version_a,
        version_b=result.version_b,
        metric_name=result.metric_name,
        higher_is_better=result.higher_is_better,
        value_a=result.value_a,
        value_b=result.value_b,
        delta=result.delta,
        b_is_better=result.b_is_better,
        blocked_by_drift=result.blocked_by_drift,
    )


@router.post("/versioning/rollback", response_model=ModelVersionRollbackResponse)
def rollback_version(
    request: ModelVersionRollbackRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    dispatcher: TrainingDispatcher = Depends(get_training_dispatcher),
) -> ModelVersionRollbackResponse:
    try:
        result = dispatcher.rollback_to_version(
            tenant, request.module_code, request.task_code, request.target_version
        )
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found") from exc

    return ModelVersionRollbackResponse(
        previous_active_version=result.previous_active_version,
        target_version=result.target_version,
        activated=result.activated,
    )

