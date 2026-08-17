"""Endpoints orientés métier : statut d'entraînement et prédictions.

Ces routes n'exposent jamais de nom de modèle, d'algorithme ni de métrique
technique. Le frontend ne connaît que des messages business et un résultat ;
il ne sait jamais quel modèle a été sélectionné ni comment.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.ai_engine import get_prediction_runtime, get_prediction_service
from backend.app.dependencies.auth import get_tenant_context
from backend.app.models import AIJob, JobStatus
from backend.app.repositories import SQLAlchemyModuleEntitlements
from backend.app.schemas.training import (
    BusinessDecisionResponse,
    BusinessOpportunityResponse,
    PortfolioDecisionsRequest,
    PortfolioOpportunitiesResponse,
    PredictionRequest,
    PredictionResponse,
    TrainingStatusResponse,
)
from backend.app.services.portfolio_decision_service import gather_portfolio_signals
from backend.app.services.portfolio_opportunity_service import build_portfolio_opportunities
from backend.app.services.prediction_runtime import (
    PredictionRuntime,
    build_decision_service,
    resolve_active_model_type,
    resolve_executor,
)
from backend.app.services.training_dispatcher import STAGE_PREPARING, STAGE_READY
from modules.entitlements import ModuleAccessDenied, ModuleAccessService
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.decision_intelligence.contracts import DecisionContext
from shared.ai_engine.exceptions import ModelNotFoundError
from shared.ai_engine.prediction.service import PredictionService

router = APIRouter(tags=["training"])


@router.get("/training-jobs/{ai_job_id}", response_model=TrainingStatusResponse)
def get_training_status(
    ai_job_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> TrainingStatusResponse:
    ai_job = db.scalar(
        select(AIJob).where(AIJob.id == ai_job_id, AIJob.company_id == tenant.company_id)
    )
    if ai_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    message = ai_job.logs or (
        STAGE_READY if ai_job.status == JobStatus.COMPLETED else STAGE_PREPARING
    )
    return TrainingStatusResponse(
        ai_job_id=ai_job.id,
        ready=ai_job.status == JobStatus.COMPLETED,
        message=message,
    )


@router.post("/predict", response_model=PredictionResponse)
def predict(
    request: PredictionRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    prediction_service: PredictionService = Depends(get_prediction_service),
) -> PredictionResponse:
    access = ModuleAccessService(SQLAlchemyModuleEntitlements(db))
    try:
        access.require_active(tenant, request.module_code)
    except ModuleAccessDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    try:
        model_type = resolve_active_model_type(db, tenant, request.module_code, request.task_code)
        outcome = prediction_service.predict(
            tenant,
            request.module_code,
            request.task_code,
            request.features,
            resolve_executor(model_type),
        )
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Your AI workspace is not ready yet.",
        ) from exc
    return PredictionResponse(result=outcome["result"], confidence=outcome.get("confidence"))


@router.post("/predict/decision", response_model=BusinessDecisionResponse)
def predict_decision(
    request: PredictionRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    runtime: PredictionRuntime = Depends(get_prediction_runtime),
) -> BusinessDecisionResponse:
    """Même prédiction que `/predict`, transformée en décision métier lisible.

    Jamais de nom de modèle, d'algorithme ni de métrique technique dans la
    réponse : uniquement titre, impact, recommandation et priorité (voir
    `shared.ai_engine.decision_intelligence`).
    """

    access = ModuleAccessService(SQLAlchemyModuleEntitlements(db))
    try:
        access.require_active(tenant, request.module_code)
    except ModuleAccessDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    try:
        decision = runtime.decide(db, tenant, request.module_code, request.task_code, request.features)
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Your AI workspace is not ready yet.",
        ) from exc

    action = decision.recommended_actions[0]
    return BusinessDecisionResponse(
        title=decision.insight.title,
        impact=decision.insight.summary,
        recommendation=f"{action.title} — {action.description}",
        priority=decision.priority.value,
    )


@router.post("/portfolio-decisions", response_model=list[BusinessDecisionResponse])
def portfolio_decisions(
    request: PortfolioDecisionsRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    prediction_service: PredictionService = Depends(get_prediction_service),
) -> list[BusinessDecisionResponse]:
    """Décisions métier agrégées sur le portefeuille client (Phase 22, BLOC B).

    Combine churn + segmentation (compte de clients à forte valeur à risque de
    départ) et recommendation (opportunités de vente croisée) — jamais une
    décision pour un client isolé. Phase 24 : ajoute demande, prix et le
    segment dominant du portefeuille (indépendamment du risque de départ).
    Réutilise le même `BusinessDecisionService` que `/predict/decision`
    (aucun second moteur de décision).
    """

    access = ModuleAccessService(SQLAlchemyModuleEntitlements(db))
    try:
        access.require_active(tenant, request.module_code)
    except ModuleAccessDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    signals = gather_portfolio_signals(db, tenant, request.module_code, prediction_service)

    if not signals:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Your AI workspace is not ready yet.",
        )

    context = DecisionContext(company_id=tenant.company_id, module_code=request.module_code)
    bundle = build_decision_service(request.module_code).build_bundle(context, signals)
    return [
        BusinessDecisionResponse(
            title=decision.insight.title,
            impact=decision.insight.summary,
            recommendation=f"{decision.recommended_actions[0].title} — {decision.recommended_actions[0].description}",
            priority=decision.priority.value,
        )
        for decision in bundle.decisions
    ]


@router.post("/portfolio-opportunities", response_model=PortfolioOpportunitiesResponse)
def portfolio_opportunities(
    request: PortfolioDecisionsRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    prediction_service: PredictionService = Depends(get_prediction_service),
) -> PortfolioOpportunitiesResponse:
    """Opportunités métier priorisées sur le portefeuille client (Phase 25).

    Le tenant est toujours résolu côté serveur (`get_tenant_context`) : aucun
    `company_id` fourni par le client n'est jamais accepté. Réutilise
    `BusinessDecisionService`/`rank_decisions()` (aucun second moteur de
    priorisation) — jamais de nom de modèle, de score ML brut ni de montant
    financier inventé dans la réponse.
    """

    access = ModuleAccessService(SQLAlchemyModuleEntitlements(db))
    try:
        access.require_active(tenant, request.module_code)
    except ModuleAccessDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    signals = gather_portfolio_signals(db, tenant, request.module_code, prediction_service)
    if not signals:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Your AI workspace is not ready yet.",
        )

    portfolio = build_portfolio_opportunities(db, tenant, request.module_code, prediction_service)
    return PortfolioOpportunitiesResponse(
        company_id=portfolio.company_id,
        opportunity_count=portfolio.opportunity_count,
        critical_count=portfolio.critical_count,
        high_count=portfolio.high_count,
        opportunities=[
            BusinessOpportunityResponse(
                id=opportunity.id,
                capability=opportunity.capability,
                title=opportunity.title,
                summary=opportunity.summary,
                direction=opportunity.direction.value,
                priority=opportunity.priority.value,
                severity=opportunity.severity.value,
                confidence=opportunity.confidence,
                estimated_impact=opportunity.estimated_impact,
                impact_unit=opportunity.impact_unit,
                recommended_action=opportunity.recommended_action,
                status=opportunity.status.value,
                created_at=opportunity.created_at.isoformat(),
            )
            for opportunity in portfolio.opportunities
        ],
    )
