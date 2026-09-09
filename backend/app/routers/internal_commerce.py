"""Protected infrastructure trigger for periodic commerce reconciliation."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status

from backend.app.config.settings import get_settings
from backend.app.dependencies.commerce import get_commerce_sync_runner
from backend.app.services.commerce_sync_runner import CommerceSyncRunner

router = APIRouter(tags=["internal-commerce"])


@router.post("/commerce/reconcile")
async def reconcile_commerce_connections(
    x_avenqo_scheduler_token: str = Header(default=""),
    runner: CommerceSyncRunner = Depends(get_commerce_sync_runner),
) -> dict[str, int]:
    configured_token = get_settings().connector_ai_scheduler_token
    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Commerce reconciliation scheduler is not configured",
        )
    if not secrets.compare_digest(x_avenqo_scheduler_token, configured_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid scheduler credentials",
        )
    return {"claimed": await runner.reconcile_active()}