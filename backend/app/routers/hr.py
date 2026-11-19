"""Routeur REST pour le module Ressources Humaines (HR AI) & Hiérarchie d'Entreprise.

Fournit la vue d'ensemble des effectifs, la cartographie des rôles et compétences,
les standards opératoires (SOP) adaptés au secteur d'activité, la gestion des congés
et les évaluations de performance.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.dependencies.subscription import require_active_subscription
from backend.app.models.base import UserRole
from backend.app.schemas.hr import (
    HREmployeeItem,
    HRLeaveItem,
    HRLeaveRequest,
    HRLeaveStatusUpdate,
    HROverviewResponse,
    HRPerformanceReviewCreate,
    HRPerformanceReviewItem,
    HRSectorSOPResponse,
    HRSkillItem,
)
from backend.app.services.hr_service import HRService

router = APIRouter(prefix="/hr", tags=["hr"])


def _check_admin_or_owner(identity: CurrentIdentity) -> None:
    role = getattr(identity.user, "role", None)
    if role not in {UserRole.OWNER, UserRole.ADMIN} and not getattr(identity.user, "is_platform_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action réservée aux administrateurs ou à la direction de l'entreprise.",
        )


@router.get("/overview", response_model=HROverviewResponse)
def get_hr_overview(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> HROverviewResponse:
    """Retourne la synthèse globale RH, indicateurs clés et goulots d'étranglement."""
    service = HRService(db)
    return service.get_overview(identity.company_id)


@router.get("/employees", response_model=list[HREmployeeItem])
def list_company_employees(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> list[HREmployeeItem]:
    """Liste exhaustive des collaborateurs, rattachement hiérarchique, statut NIP et charges de travail."""
    service = HRService(db)
    return service.list_employees(identity.company_id)


@router.get("/job-descriptions", response_model=HRSectorSOPResponse)
def get_job_descriptions_and_sops(
    sector: str | None = Query(None, description="Secteur d'activité spécifique"),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> HRSectorSOPResponse:
    """Retourne les fiches de postes et standards opératoires d'excellence (SOP) pour le secteur."""
    service = HRService(db)
    return service.get_job_descriptions(identity.company_id, sector=sector)


@router.get("/skills", response_model=list[HRSkillItem])
def get_skills_matrix(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> list[HRSkillItem]:
    """Retourne la matrice des compétences techniques, relationnelles et de sécurité."""
    service = HRService(db)
    return service.get_skills_matrix(identity.company_id)


@router.get("/leaves", response_model=list[HRLeaveItem])
def list_leaves(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> list[HRLeaveItem]:
    """Consulte l'historique et les demandes en attente de congés / absences."""
    service = HRService(db)
    return service.list_leaves(identity.company_id)


@router.post("/leaves", response_model=HRLeaveItem, status_code=status.HTTP_201_CREATED)
def submit_leave_request(
    request: HRLeaveRequest,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> HRLeaveItem:
    """Soumet une nouvelle demande de congé ou absence pour l'utilisateur connecté."""
    service = HRService(db)
    return service.create_leave(
        company_id=identity.company_id,
        user_id=identity.user_id,
        leave_type=request.leave_type,
        start_date=request.start_date,
        end_date=request.end_date,
        days_count=request.days_count,
        reason=request.reason,
    )


@router.put("/leaves/{leave_id}/status", response_model=HRLeaveItem)
def update_leave_status(
    leave_id: UUID,
    payload: HRLeaveStatusUpdate,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> HRLeaveItem:
    """Approuve ou refuse une demande de congé. Action réservée à la direction."""
    _check_admin_or_owner(identity)
    if payload.status not in {"approved", "rejected", "pending"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Statut invalide. Utilisez 'approved' ou 'rejected'.",
        )
    service = HRService(db)
    try:
        return service.update_leave_status(
            company_id=identity.company_id,
            leave_id=leave_id,
            approver_user_id=identity.user_id,
            new_status=payload.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/reviews", response_model=list[HRPerformanceReviewItem])
def list_performance_reviews(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> list[HRPerformanceReviewItem]:
    """Consulte les revues de performance et bilans de coaching."""
    service = HRService(db)
    return service.list_reviews(identity.company_id)


@router.post("/reviews", response_model=HRPerformanceReviewItem, status_code=status.HTTP_201_CREATED)
def create_performance_review(
    payload: HRPerformanceReviewCreate,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> HRPerformanceReviewItem:
    """Enregistre une revue de performance pour un collaborateur. Action réservée à la direction."""
    _check_admin_or_owner(identity)
    service = HRService(db)
    return service.create_review(
        company_id=identity.company_id,
        user_id=payload.employee_id,
        reviewer_user_id=identity.user_id,
        review_period=payload.review_period,
        rating=payload.rating,
        strengths=payload.strengths,
        growth_areas=payload.growth_areas,
        goals=payload.goals,
    )
