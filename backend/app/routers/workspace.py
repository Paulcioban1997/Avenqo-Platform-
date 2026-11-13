"""Espace employé : équipe, tâches, invitations, guidance."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_account_notifier, get_current_identity
from backend.app.models import SandboxMailboxMessage, UserRole
from backend.app.core.permissions import permissions_for
from backend.app.schemas.workspace_sources import (
    WorkspaceSourceSelectionRequest,
    WorkspaceSourceSelectionResponse,
)
from backend.app.services.account_notifications import AccountNotifier
from backend.app.routers.employees import plan_limit_exception
from backend.app.services.plan_limits_service import PlanLimitReached
from backend.app.services.retail_source_service import (
    CrossTenantSourceAccessDenied,
    RetailSourceNotFound,
    RetailSourceService,
)
from backend.app.services.workspace_service import MailNotConfigured, WorkspaceError, WorkspaceService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/workspace", tags=["workspace"])


def _delivery_channel(service: WorkspaceService) -> str:
    notifier = getattr(service, "_notifier", None)
    if type(notifier).__name__ == "SandboxCaptureAccountNotifier":
        return "sandbox_mailbox"
    return "email"


@router.get("/sandbox-mailbox")
def sandbox_mailbox(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> dict:
    """Messages captured for this company. Production has no such mailbox."""
    if get_settings().environment.lower() in {"production", "prod"}:
        raise HTTPException(status_code=404, detail="Introuvable")
    if "users:manage" not in permissions_for(identity.user.role):
        raise HTTPException(status_code=403, detail="Permission insuffisante")
    rows = db.scalars(
        select(SandboxMailboxMessage)
        .where(SandboxMailboxMessage.company_id == identity.user.company_id)
        .order_by(SandboxMailboxMessage.created_at.desc())
        .limit(20)
    ).all()
    return {
        "external_delivery": False,
        "messages": [
            {
                "id": str(row.id),
                "recipient": row.recipient,
                "subject": row.subject,
                "body": row.body,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


class ProfileUpdate(BaseModel):
    job_title: str | None = Field(default=None, max_length=120)
    department: str | None = Field(default=None, max_length=120)


class ResponsibilityCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=2000)


class TaskCreate(BaseModel):
    assignee_user_id: UUID
    title: str = Field(min_length=2, max_length=220)
    description: str | None = Field(default=None, max_length=4000)
    priority: str = "medium"
    due_at: datetime | None = None


class InvitationCreate(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.USER
    job_title: str = Field(default="Employee", max_length=120)
    department: str | None = Field(default=None, max_length=120)


class InvitationAccept(BaseModel):
    token: str | None = Field(default=None, max_length=512)
    code: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=128)


class BulkInvitationCreate(BaseModel):
    emails: list[EmailStr] = Field(min_length=1, max_length=50)
    role: UserRole = UserRole.USER
    job_title: str = Field(default="Employee", max_length=120)
    department: str | None = Field(default=None, max_length=120)


def _service(
    db: Session = Depends(get_db),
    notifier: AccountNotifier = Depends(get_account_notifier),
) -> WorkspaceService:
    return WorkspaceService(db, notifier)


def _http(exc: WorkspaceError) -> HTTPException:
    return HTTPException(400, str(exc))


@router.get("/team")
def team(identity: CurrentIdentity = Depends(get_current_identity), service: WorkspaceService = Depends(_service)) -> list[dict]:
    return service.list_team(identity.user)


@router.get("/org-chart")
def org_chart(identity: CurrentIdentity = Depends(get_current_identity), service: WorkspaceService = Depends(_service)) -> dict:
    return service.org_chart(identity.user)


@router.patch("/employees/{employee_id}/profile")
def update_profile(
    employee_id: UUID,
    payload: ProfileUpdate,
    identity: CurrentIdentity = Depends(get_current_identity),
    service: WorkspaceService = Depends(_service),
) -> dict:
    try:
        user = service.assign_profile(identity.user, employee_id, job_title=payload.job_title, department=payload.department)
    except WorkspaceError as exc:
        raise _http(exc) from exc
    return {"id": str(user.id), "job_title": user.job_title, "department": user.department}


@router.get("/responsibilities")
def responsibilities(
    user_id: UUID | None = None,
    identity: CurrentIdentity = Depends(get_current_identity),
    service: WorkspaceService = Depends(_service),
) -> list[dict]:
    try:
        rows = service.list_responsibilities(identity.user, user_id)
    except WorkspaceError as exc:
        raise HTTPException(403, str(exc)) from exc
    return [{"id": str(row.id), "user_id": str(row.user_id), "title": row.title, "description": row.description} for row in rows]


@router.post("/employees/{employee_id}/responsibilities", status_code=201)
def add_responsibility(
    employee_id: UUID,
    payload: ResponsibilityCreate,
    identity: CurrentIdentity = Depends(get_current_identity),
    service: WorkspaceService = Depends(_service),
) -> dict:
    try:
        row = service.add_responsibility(identity.user, employee_id, payload.title, payload.description)
    except WorkspaceError as exc:
        raise HTTPException(403, str(exc)) from exc
    return {"id": str(row.id), "title": row.title}


@router.get("/tasks")
def tasks(identity: CurrentIdentity = Depends(get_current_identity), service: WorkspaceService = Depends(_service)) -> list[dict]:
    return [WorkspaceService._task_payload(row) for row in service.list_tasks(identity.user)]


@router.post("/tasks", status_code=201)
def create_task(
    payload: TaskCreate,
    identity: CurrentIdentity = Depends(get_current_identity),
    service: WorkspaceService = Depends(_service),
) -> dict:
    try:
        row = service.create_task(
            identity.user,
            assignee_user_id=payload.assignee_user_id,
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            due_at=payload.due_at,
        )
    except WorkspaceError as exc:
        raise HTTPException(403, str(exc)) from exc
    return WorkspaceService._task_payload(row)


@router.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: UUID,
    identity: CurrentIdentity = Depends(get_current_identity),
    service: WorkspaceService = Depends(_service),
) -> dict:
    try:
        row = service.complete_task(identity.user, task_id)
    except WorkspaceError as exc:
        raise HTTPException(404 if "introuvable" in str(exc) else 403, str(exc)) from exc
    return WorkspaceService._task_payload(row)


@router.post("/invitations", status_code=201)
def invite(
    payload: InvitationCreate,
    identity: CurrentIdentity = Depends(get_current_identity),
    service: WorkspaceService = Depends(_service),
) -> dict:
    try:
        row = service.invite(identity.user, str(payload.email), payload.role, payload.job_title, payload.department)
    except MailNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc
    except PlanLimitReached as exc:
        raise plan_limit_exception(exc) from exc
    return {
        "id": str(row.id),
        "email": row.email,
        "expires_at": row.expires_at.isoformat(),
        "delivery": _delivery_channel(service),
    }


@router.post("/invitations/bulk", status_code=201)
def invite_bulk(
    payload: BulkInvitationCreate,
    identity: CurrentIdentity = Depends(get_current_identity),
    service: WorkspaceService = Depends(_service),
) -> dict:
    try:
        rows = service.invite_bulk(
            identity.user,
            [str(e) for e in payload.emails],
            payload.role,
            payload.job_title,
            payload.department,
        )
    except MailNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc
    except PlanLimitReached as exc:
        raise plan_limit_exception(exc) from exc
    return {
        "invitations": [
            {
                "id": str(r.id),
                "email": r.email,
                "expires_at": r.expires_at.isoformat(),
                "delivery": _delivery_channel(service),
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.post("/invitations/accept", status_code=201)
def accept_invitation(payload: InvitationAccept, service: WorkspaceService = Depends(_service)) -> dict:
    try:
        user = service.accept_invitation(
            payload.token,
            payload.first_name,
            payload.last_name,
            payload.password,
            code=payload.code,
            email=str(payload.email) if payload.email else None,
        )
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc
    except PlanLimitReached as exc:
        raise plan_limit_exception(exc) from exc
    return {"id": str(user.id), "email": user.email, "company_id": str(user.company_id)}


class GuidanceAsk(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    confirm_token: str | None = None


@router.get("/guidance")
def guidance(identity: CurrentIdentity = Depends(get_current_identity), service: WorkspaceService = Depends(_service)) -> dict:
    return service.personal_briefing(identity.user)


@router.post("/guidance/ask")
def ask_guidance(
    payload: GuidanceAsk,
    identity: CurrentIdentity = Depends(get_current_identity),
    service: WorkspaceService = Depends(_service),
) -> dict:
    try:
        return service.answer_question(identity.user, payload.question, confirm_token=payload.confirm_token)
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/sources/selection", response_model=WorkspaceSourceSelectionResponse)
def get_sources_selection(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> WorkspaceSourceSelectionResponse:
    """Retourne la configuration multi-sources actuelle de l'entreprise."""
    if "data:read" not in permissions_for(identity.user.role):
        raise HTTPException(status_code=403, detail="Permission refusée: data:read requise")
    tenant = TenantContext(company_id=identity.company_id, user_id=identity.user_id)
    service = RetailSourceService(db)
    result = service.get_workspace_selection(tenant)
    return WorkspaceSourceSelectionResponse.model_validate(result)


@router.post("/sources/selection", response_model=WorkspaceSourceSelectionResponse)
def set_sources_selection(
    payload: WorkspaceSourceSelectionRequest,
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> WorkspaceSourceSelectionResponse:
    """Met à jour le mode et la sélection multi-sources pour l'entreprise."""
    if "data:manage" not in permissions_for(identity.user.role):
        raise HTTPException(status_code=403, detail="Permission refusée: data:manage requise")
    tenant = TenantContext(company_id=identity.company_id, user_id=identity.user_id)
    service = RetailSourceService(db)
    try:
        result = service.set_workspace_selection(
            tenant,
            mode=payload.mode,
            selected_source_ids=payload.selected_source_ids,
        )
    except CrossTenantSourceAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RetailSourceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return WorkspaceSourceSelectionResponse.model_validate(result)
