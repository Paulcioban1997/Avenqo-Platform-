"""Routeur REST pour le module Ressources Humaines (HR AI) & Hiérarchie d'Entreprise.

Fournit la vue d'ensemble des effectifs, la cartographie des rôles et compétences vérifiées,
les standards opératoires (SOP) adaptés au secteur d'activité, la gestion sécurisée des congés
et les évaluations de performance avec respect strict du RBAC et de l'isolation multi-tenant.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.models.base import UserRole
from backend.app.models.user import User
from backend.app.models.workspace import EmployeeLeave, EmployeeSkill
from backend.app.schemas.hr import (
    HREmployeeItem,
    HRLeaveItem,
    HRLeaveRequest,
    HRLeaveStatusUpdate,
    HROverviewResponse,
    HRPerformanceReviewCreate,
    HRPerformanceReviewItem,
    HRSectorSOPResponse,
    HRSkillDeclareRequest,
    HRSkillItem,
    HRSkillVerifyRequest,
)
from backend.app.services.hr_service import HRService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/hr", tags=["hr"])


def require_hr_entitlement(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> CurrentIdentity:
    """Vérification stricte de l'activation du module HR AI et de l'isolation tenant."""
    # Règle P0 Sécurité : Platform Admin n'a aucun accès automatique aux dossiers RH privés
    if getattr(identity.user, "is_platform_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Les administrateurs de la plateforme n'ont aucun accès automatique aux dossiers RH privés.",
        )

    tenant = TenantContext(identity.company_id)
    if not ModuleEntitlementService(db).can_use_module(tenant, "hr"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "module_inactive",
                "message": "Le module HR AI n'est pas activé pour cette entreprise. Veuillez l'activer dans vos paramètres ou mettre à niveau votre forfait.",
                "module": "hr",
            },
        )
    return identity


def _get_user_role(identity: CurrentIdentity) -> UserRole:
    return getattr(identity.user, "role", UserRole.USER)


def _is_owner_or_admin(identity: CurrentIdentity) -> bool:
    return _get_user_role(identity) in {UserRole.OWNER, UserRole.ADMIN}


def _is_manager(identity: CurrentIdentity) -> bool:
    return _get_user_role(identity) in {UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER}


@router.get("/overview", response_model=HROverviewResponse)
def get_hr_overview(
    identity: CurrentIdentity = Depends(require_hr_entitlement),
    db: Session = Depends(get_db),
) -> HROverviewResponse:
    """Retourne la synthèse globale RH, indicateurs clés et goulots d'étranglement."""
    service = HRService(db)
    return service.get_overview(identity.company_id)


@router.get("/employees", response_model=list[HREmployeeItem])
def list_company_employees(
    identity: CurrentIdentity = Depends(require_hr_entitlement),
    db: Session = Depends(get_db),
) -> list[HREmployeeItem]:
    """Liste les collaborateurs de l'entreprise avec filtrage selon les privilèges du rôle."""
    service = HRService(db)
    all_employees = service.list_employees(identity.company_id)

    # Si manager, admin ou owner : vue complète
    if _is_manager(identity):
        return all_employees

    # Si employé standard : annuaire épuré sans données de sécurité privées (pas de NIP ni téléphone)
    return [
        HREmployeeItem(
            id=e.id,
            first_name=e.first_name,
            last_name=e.last_name,
            email=e.email,
            phone=None,
            role=e.role,
            job_title=e.job_title,
            department=e.department,
            hierarchy_level=e.hierarchy_level,
            is_active=e.is_active,
            has_voice_pin=False,
            open_tasks_count=0,
            completed_tasks_count=0,
        )
        for e in all_employees
    ]


@router.get("/job-descriptions", response_model=HRSectorSOPResponse)
def get_job_descriptions_and_sops(
    sector: str | None = Query(None, description="Secteur d'activité spécifique"),
    identity: CurrentIdentity = Depends(require_hr_entitlement),
    db: Session = Depends(get_db),
) -> HRSectorSOPResponse:
    """Retourne les fiches de postes et standards opératoires d'excellence (SOP) pour le secteur."""
    service = HRService(db)
    return service.get_job_descriptions(identity.company_id, sector=sector)


@router.get("/skills", response_model=list[HRSkillItem])
def get_skills_matrix(
    identity: CurrentIdentity = Depends(require_hr_entitlement),
    db: Session = Depends(get_db),
) -> list[HRSkillItem]:
    """Retourne la matrice des compétences selon le périmètre d'autorisation du rôle."""
    service = HRService(db)
    if _is_owner_or_admin(identity):
        return service.get_skills_matrix(identity.company_id)
    elif _is_manager(identity):
        caller_dept = getattr(identity.user, "department", None)
        return service.get_skills_matrix(identity.company_id, department=caller_dept)
    else:
        return service.get_skills_matrix(identity.company_id, user_id=identity.user_id)


@router.post("/skills/declare", response_model=HRSkillItem, status_code=status.HTTP_201_CREATED)
def declare_skill(
    payload: HRSkillDeclareRequest,
    identity: CurrentIdentity = Depends(require_hr_entitlement),
    db: Session = Depends(get_db),
) -> HRSkillItem:
    """Auto-déclare une compétence pour le collaborateur connecté (statut self_declared)."""
    service = HRService(db)
    return service.declare_skill(
        company_id=identity.company_id,
        user_id=identity.user_id,
        name=payload.name,
        category=payload.category,
        level=payload.level,
        evidence_url_or_note=payload.evidence_url_or_note,
    )


@router.post("/skills/{skill_id}/verify", response_model=HRSkillItem)
def verify_skill(
    skill_id: UUID,
    payload: HRSkillVerifyRequest,
    identity: CurrentIdentity = Depends(require_hr_entitlement),
    db: Session = Depends(get_db),
) -> HRSkillItem:
    """Certifie et valide formellement une compétence. Réservé aux managers et à la direction."""
    if not _is_manager(identity):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les managers ou administrateurs peuvent certifier une compétence.",
        )

    # 1. Vérifier l'existence et l'isolation tenant
    skill = db.get(EmployeeSkill, skill_id)
    if skill is None or skill.company_id != identity.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compétence introuvable pour cette entreprise.",
        )

    # 2. Interdiction absolue d'auto-certification
    if skill.user_id == identity.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Un gestionnaire ne peut pas certifier ses propres compétences.",
        )

    # 3. Cloisonnement départemental : un manager hors Direction/Admin ne peut certifier que son département
    if not _is_owner_or_admin(identity):
        caller_dept = getattr(identity.user, "department", None)
        target_user = db.get(User, skill.user_id)
        target_dept = getattr(target_user, "department", None) if target_user else None
        if not caller_dept or caller_dept != target_dept:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous ne pouvez certifier que les compétences des collaborateurs de votre département.",
            )

    service = HRService(db)
    try:
        return service.verify_skill(
            company_id=identity.company_id,
            skill_id=skill_id,
            verifier_user_id=identity.user_id,
            level=payload.level,
            evidence_url_or_note=payload.evidence_url_or_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/leaves", response_model=list[HRLeaveItem])
def list_leaves(
    identity: CurrentIdentity = Depends(require_hr_entitlement),
    db: Session = Depends(get_db),
) -> list[HRLeaveItem]:
    """Consulte les congés en respectant le périmètre RBAC strict."""
    service = HRService(db)
    role = _get_user_role(identity)

    # 1. Direction / Administrateurs RH : accès à l'ensemble des congés de l'organisation
    if role in {UserRole.OWNER, UserRole.ADMIN}:
        return service.list_leaves(identity.company_id)

    # 2. Managers : accès à leur département autorisé + leurs propres congés
    if role == UserRole.MANAGER:
        caller_dept = getattr(identity.user, "department", None)
        dept_leaves = service.list_leaves(identity.company_id, department=caller_dept) if caller_dept else []
        own_leaves = service.list_leaves(identity.company_id, user_id=identity.user_id)
        seen_ids = set()
        merged: list[HRLeaveItem] = []
        for l in dept_leaves + own_leaves:
            if l.id not in seen_ids:
                seen_ids.add(l.id)
                merged.append(l)
        return merged

    # 3. Employés standards : STRICTEMENT leurs propres demandes de congés
    return service.list_leaves(identity.company_id, user_id=identity.user_id)


@router.post("/leaves", response_model=HRLeaveItem, status_code=status.HTTP_201_CREATED)
def submit_leave_request(
    request: HRLeaveRequest,
    identity: CurrentIdentity = Depends(require_hr_entitlement),
    db: Session = Depends(get_db),
) -> HRLeaveItem:
    """Soumet une nouvelle demande de congé pour le collaborateur authentifié (anti-IDOR)."""
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
    identity: CurrentIdentity = Depends(require_hr_entitlement),
    db: Session = Depends(get_db),
) -> HRLeaveItem:
    """Approuve ou refuse une demande de congé. Contrôle RBAC strict et périmètre managérial."""
    if payload.status not in {"approved", "rejected", "pending"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Statut invalide. Utilisez 'approved' ou 'rejected'.",
        )

    leave = db.get(EmployeeLeave, leave_id)
    if leave is None or leave.company_id != identity.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demande de congé introuvable pour cette entreprise.",
        )

    # Règle de séparation des devoirs : un employé ne peut jamais approuver ses propres congés
    if leave.user_id == identity.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez pas approuver votre propre demande de congé.",
        )

    # Vérification des autorisations
    if not _is_manager(identity):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les managers et administrateurs peuvent valider une demande de congé.",
        )

    # Si manager non admin : restreint à son propre département
    if _get_user_role(identity) == UserRole.MANAGER and not _is_owner_or_admin(identity):
        target_user = db.get(User, leave.user_id)
        caller_dept = getattr(identity.user, "department", None)
        if not target_user or not caller_dept or target_user.department != caller_dept:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'êtes autorisé à valider les congés que des collaborateurs de votre département.",
            )

    service = HRService(db)
    return service.update_leave_status(
        company_id=identity.company_id,
        leave_id=leave_id,
        approver_user_id=identity.user_id,
        new_status=payload.status,
    )


@router.get("/reviews", response_model=list[HRPerformanceReviewItem])
def list_performance_reviews(
    identity: CurrentIdentity = Depends(require_hr_entitlement),
    db: Session = Depends(get_db),
) -> list[HRPerformanceReviewItem]:
    """Consulte les revues de performance avec isolation RBAC stricte."""
    service = HRService(db)
    role = _get_user_role(identity)

    # 1. Direction / Administrateurs RH : accès organisationnel
    if role in {UserRole.OWNER, UserRole.ADMIN}:
        return service.list_reviews(identity.company_id)

    # 2. Managers : revues de leur département + leurs propres revues
    if role == UserRole.MANAGER:
        caller_dept = getattr(identity.user, "department", None)
        dept_reviews = service.list_reviews(identity.company_id, department=caller_dept) if caller_dept else []
        own_reviews = service.list_reviews(identity.company_id, user_id=identity.user_id)
        seen_ids = set()
        merged: list[HRPerformanceReviewItem] = []
        for r in dept_reviews + own_reviews:
            if r.id not in seen_ids:
                seen_ids.add(r.id)
                merged.append(r)
        return merged

    # 3. Employés standards : STRICTEMENT leurs propres évaluations de performance
    return service.list_reviews(identity.company_id, user_id=identity.user_id)


@router.post("/reviews", response_model=HRPerformanceReviewItem, status_code=status.HTTP_201_CREATED)
def create_performance_review(
    payload: HRPerformanceReviewCreate,
    identity: CurrentIdentity = Depends(require_hr_entitlement),
    db: Session = Depends(get_db),
) -> HRPerformanceReviewItem:
    """Enregistre une revue de performance pour un collaborateur sous contrôle managérial."""
    # Règle d'intégrité : un collaborateur ne peut pas s'auto-évaluer
    if payload.employee_id == identity.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Un collaborateur ne peut pas rédiger sa propre évaluation de performance.",
        )

    # Seuls les managers et la direction peuvent évaluer
    if not _is_manager(identity):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les managers et administrateurs peuvent rédiger une évaluation.",
        )

    target_user = db.get(User, payload.employee_id)
    if target_user is None or target_user.company_id != identity.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collaborateur introuvable pour cette entreprise.",
        )

    # Contrôle de périmètre pour manager
    if _get_user_role(identity) == UserRole.MANAGER and not _is_owner_or_admin(identity):
        caller_dept = getattr(identity.user, "department", None)
        if not caller_dept or target_user.department != caller_dept:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'êtes autorisé à évaluer que les collaborateurs de votre département.",
            )

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
        is_demo=payload.is_demo,
    )
