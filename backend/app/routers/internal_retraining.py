"""Endpoint interne — Auto Retraining Enterprise (Phase 8).

Ce routeur n'est jamais destiné au frontend utilisateur : il n'existe aucun
bouton "Train"/"Retrain" dans l'application. Il sert deux usages, tous deux
internes à l'infrastructure :

1. Un déclenchement planifié (scheduled retraining) : un CronJob Kubernetes,
   Celery beat, ou tout autre ordonnanceur externe appelle périodiquement cet
   endpoint pour chaque (tenant, module, tâche) actif.
2. Un déclenchement manuel via l'API interne (manual trigger) : une opération
   d'exploitation explicite, jamais exposée à l'utilisateur final.

Dans les deux cas, la décision réelle de ré-entraîner (ou non) reste
entièrement pilotée par `shared/ai_engine/retraining` : cet endpoint ne fait
que déléguer à `TrainingDispatcher.dispatch_retraining_check`, qui applique
les règles configurables et n'enfile un job que si nécessaire.

Monté à part de `api_router` (préfixe `/internal`, jamais `/api/v1`) afin de
rester clairement distinct des routes utilisateur.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.dependencies.auth import get_tenant_context
from backend.app.dependencies.training import get_training_dispatcher
from backend.app.schemas.training import RetrainingCheckRequest, RetrainingCheckResponse
from backend.app.services.training_dispatcher import TrainingDispatcher
from shared.ai_engine.contracts import TenantContext

router = APIRouter(tags=["internal-retraining"])


@router.post("/retraining/check", response_model=RetrainingCheckResponse)
def check_retraining(
    request: RetrainingCheckRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    dispatcher: TrainingDispatcher = Depends(get_training_dispatcher),
) -> RetrainingCheckResponse:
    ai_job = dispatcher.dispatch_retraining_check(
        tenant, request.module_code, request.task_code, manual=True
    )
    return RetrainingCheckResponse(queued=ai_job is not None, ai_job_id=ai_job.id if ai_job else None)
