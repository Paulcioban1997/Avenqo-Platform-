"""Protected infrastructure trigger for periodic commerce reconciliation."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.dependencies.commerce import get_commerce_sync_runner
from backend.app.dependencies.internal import require_internal_service_token
from backend.app.services.commerce_sync_runner import CommerceSyncRunner

router = APIRouter(tags=["internal-commerce"])


@router.post("/commerce/reconcile", dependencies=[Depends(require_internal_service_token)])
async def reconcile_commerce_connections(
    runner: CommerceSyncRunner = Depends(get_commerce_sync_runner),
) -> dict[str, int]:
    return {"claimed": await runner.reconcile_active()}
