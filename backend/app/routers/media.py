from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.dependencies.subscription import require_active_subscription
from backend.app.services.media_generation_service import MediaGenerationService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/media", tags=["media"])


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=8, max_length=4000)
    kind: str = "marketing_text"


def _service(db: Session = Depends(get_db)) -> MediaGenerationService:
    return MediaGenerationService(db)


@router.get("/generations")
def history(
    identity: CurrentIdentity = Depends(get_current_identity),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: MediaGenerationService = Depends(_service),
    _: None = Depends(require_active_subscription),
) -> list[dict]:
    if not ModuleEntitlementService(db).can_use_module(tenant, "media") and not ModuleEntitlementService(db).can_use_module(tenant, "marketing"):
        raise HTTPException(403, {"code": "module_inactive", "module": "media"})
    return [
        {
            "id": str(row.id),
            "kind": row.kind,
            "prompt": row.prompt,
            "output_text": row.output_text,
            "provider": row.provider,
            "credits_used": row.credits_used,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in service.history(identity.user)
    ]


@router.post("/generations", status_code=201)
def generate(
    payload: GenerateRequest,
    identity: CurrentIdentity = Depends(get_current_identity),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    service: MediaGenerationService = Depends(_service),
    _: None = Depends(require_active_subscription),
) -> dict:
    entitlements = ModuleEntitlementService(db)
    if not entitlements.can_use_module(tenant, "media") and not entitlements.can_use_module(tenant, "marketing"):
        raise HTTPException(403, {"code": "module_inactive", "module": "media"})
    row = service.generate(identity.user, payload.prompt, payload.kind)
    return {
        "id": str(row.id),
        "output_text": row.output_text,
        "provider": row.provider,
        "credits_used": row.credits_used,
    }
