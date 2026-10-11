from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.dependencies.subscription import require_active_subscription
from backend.app.services.automation_service import AutomationError, AutomationService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/automations", tags=["automations"])


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    trigger_type: str
    action_type: str
    condition: dict = Field(default_factory=dict)
    action: dict = Field(default_factory=dict)


class WorkflowRun(BaseModel):
    idempotency_key: str = Field(min_length=4, max_length=120)
    payload: dict = Field(default_factory=dict)


def _service(db: Session = Depends(get_db)) -> AutomationService:
    return AutomationService(db)


def _gate(db: Session, tenant: TenantContext) -> None:
    if not ModuleEntitlementService(db).can_use_module(tenant, "workflow"):
        raise HTTPException(403, {"code": "module_inactive", "module": "workflow"})


@router.get("")
def list_workflows(
    identity: CurrentIdentity = Depends(get_current_identity),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: AutomationService = Depends(_service),
    _: None = Depends(require_active_subscription),
) -> list[dict]:
    _gate(db, tenant)
    return [
        {
            "id": str(row.id),
            "name": row.name,
            "trigger_type": row.trigger_type,
            "action_type": row.action_type,
            "is_enabled": row.is_enabled,
            "last_status": row.last_status,
        }
        for row in service.list_workflows(identity.user.company_id)
    ]


@router.post("", status_code=201)
def create_workflow(
    payload: WorkflowCreate,
    identity: CurrentIdentity = Depends(get_current_identity),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: AutomationService = Depends(_service),
    _: None = Depends(require_active_subscription),
) -> dict:
    _gate(db, tenant)
    try:
        row = service.create_workflow(
            identity.user,
            name=payload.name,
            trigger_type=payload.trigger_type,
            action_type=payload.action_type,
            condition=payload.condition,
            action=payload.action,
        )
    except AutomationError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"id": str(row.id), "name": row.name}


@router.post("/{workflow_id}/run")
def run_workflow(
    workflow_id: UUID,
    payload: WorkflowRun,
    identity: CurrentIdentity = Depends(get_current_identity),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: AutomationService = Depends(_service),
    _: None = Depends(require_active_subscription),
) -> dict:
    _gate(db, tenant)
    try:
        run = service.run(identity.user, workflow_id, idempotency_key=payload.idempotency_key, payload=payload.payload)
    except AutomationError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"id": str(run.id), "status": run.status, "detail": run.detail}
