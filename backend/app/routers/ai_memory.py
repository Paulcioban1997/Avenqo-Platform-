from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.ai.memory.service import AvenqoMemoryService
from backend.app.dependencies.ai_memory import get_memory_service
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.dependencies.ai_authorization import get_active_ai_membership
from backend.app.schemas.ai_memory import (
    MemoryConfigResponse,
    MemoryCreateRequest,
    MemoryListResponse,
    MemoryResponse,
    MemorySearchRequest,
    MemoryUpdateRequest,
)
from shared.ai_engine.contracts import TenantContext

router = APIRouter(
    prefix="/ai/memories",
    tags=["enterprise-memory"],
    dependencies=[Depends(get_active_ai_membership)],
)


@router.get("/config", response_model=MemoryConfigResponse)
async def get_config(
    memory_service: AvenqoMemoryService = Depends(get_memory_service),
) -> MemoryConfigResponse:
    settings = memory_service._settings
    return MemoryConfigResponse(
        enabled=memory_service.is_enabled,
        backend=settings.avenqo_memory_backend,
        max_context_items=settings.avenqo_memory_max_context_items,
    )


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    scope: str | None = Query(default=None, pattern="^(user|company)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    memory_service: AvenqoMemoryService = Depends(get_memory_service),
) -> MemoryListResponse:
    records = memory_service.list_memories(
        tenant_id=tenant.company_id,
        user_id=identity.user.id,
        scope=scope,
        limit=limit,
        offset=offset,
    )
    return MemoryListResponse(
        memories=[MemoryResponse.model_validate(r) for r in records],
        total=len(records),
    )


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    request: MemoryCreateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    membership=Depends(get_active_ai_membership),
    memory_service: AvenqoMemoryService = Depends(get_memory_service),
) -> MemoryResponse:
    if request.scope == "company" and membership.role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent enregistrer des mémoires partagées avec l'entreprise.",
        )
    try:
        record = memory_service.add_memory(
            tenant_id=tenant.company_id,
            user_id=identity.user.id,
            content=request.content,
            scope=request.scope,
            memory_type=request.memory_type,
            source_module=request.source_module,
            conversation_id=request.conversation_id,
            metadata=request.metadata,
        )
        return MemoryResponse.model_validate(record)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/search", response_model=list[MemoryResponse])
async def search_memories(
    request: MemorySearchRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    memory_service: AvenqoMemoryService = Depends(get_memory_service),
) -> list[MemoryResponse]:
    records = memory_service.search_memories(
        tenant_id=tenant.company_id,
        user_id=identity.user.id,
        query=request.query,
        limit=request.limit,
        scope=request.scope,
        include_company_shared=request.include_company_shared,
    )
    return [MemoryResponse.model_validate(r) for r in records]


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    memory_service: AvenqoMemoryService = Depends(get_memory_service),
) -> MemoryResponse:
    record = memory_service.get_memory(tenant.company_id, identity.user.id, memory_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mémoire introuvable.")
    return MemoryResponse.model_validate(record)


@router.patch("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: UUID,
    request: MemoryUpdateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    membership=Depends(get_active_ai_membership),
    memory_service: AvenqoMemoryService = Depends(get_memory_service),
) -> MemoryResponse:
    existing = memory_service.get_memory(tenant.company_id, identity.user.id, memory_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mémoire introuvable.")
    if existing.memory_scope == "company" and membership.role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent modifier les mémoires partagées.",
        )
    record = memory_service.update_memory(
        tenant_id=tenant.company_id,
        user_id=identity.user.id,
        memory_id=memory_id,
        content=request.content,
        scope=request.scope,
        memory_type=request.memory_type,
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mémoire introuvable.")
    return MemoryResponse.model_validate(record)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    membership=Depends(get_active_ai_membership),
    memory_service: AvenqoMemoryService = Depends(get_memory_service),
) -> None:
    existing = memory_service.get_memory(tenant.company_id, identity.user.id, memory_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mémoire introuvable.")
    if existing.memory_scope == "company" and membership.role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs peuvent supprimer les mémoires partagées.",
        )
    deleted = memory_service.delete_memory(tenant.company_id, identity.user.id, memory_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mémoire introuvable.")


@router.delete("", status_code=status.HTTP_200_OK)
async def delete_all_memories(
    scope: str | None = Query(default=None, pattern="^(user|company)$"),
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    membership=Depends(get_active_ai_membership),
    memory_service: AvenqoMemoryService = Depends(get_memory_service),
) -> dict[str, int]:
    # Non-admins can only clear their private user memories
    target_user_id = identity.user.id
    if scope == "company" or scope is None:
        if membership.role not in {"owner", "admin"}:
            scope = "user"
            target_user_id = identity.user.id
        else:
            target_user_id = None if scope == "company" else identity.user.id

    count = memory_service.delete_tenant_memories(
        tenant_id=tenant.company_id,
        user_id=target_user_id,
        scope=scope,
    )
    return {"deleted_count": count}
