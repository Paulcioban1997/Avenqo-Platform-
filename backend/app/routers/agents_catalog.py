"""Catalogue des agents réellement enregistrés — pas une flotte fictive."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.assistants.registry import AssistantRegistry, agent_entitlements
from backend.app.database import get_db
from backend.app.dependencies.assistants import get_assistant_registry
from backend.app.dependencies.auth import get_tenant_context
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
def list_agents(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    registry: AssistantRegistry = Depends(get_assistant_registry),
) -> dict:
    active = frozenset(ModuleEntitlementService(db).get_active_modules(tenant))
    authorized = registry.list_authorized(active)
    authorized_slugs = {item.slug for item in authorized}
    return {
        "active_modules": sorted(active),
        "agents": [
            {
                "slug": item.slug,
                "name_key": item.name_key,
                "status": item.status.value,
                "module_code": item.module_code,
                "executable": item.status.is_executable,
            }
            for item in authorized
        ],
        "unavailable_agents": [
            {
                "slug": item.slug,
                "name_key": item.name_key,
                "reason": "module_inactive",
                "required": sorted(agent_entitlements(item)),
            }
            for item in registry.list_available()
            if item.slug not in authorized_slugs
        ],
    }
