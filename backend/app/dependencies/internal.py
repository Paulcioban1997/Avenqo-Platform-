"""Service-to-service authentication for `/internal/*` routes."""

from __future__ import annotations

import secrets
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.database import get_db
from backend.app.models import Company
from shared.ai_engine.contracts import TenantContext


def require_internal_service_token(x_avenqo_scheduler_token: str = Header(default="")) -> None:
    """User JWTs are never accepted here: only the infrastructure scheduler token."""

    configured_token = get_settings().connector_ai_scheduler_token
    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal scheduler is not configured",
        )
    if not secrets.compare_digest(x_avenqo_scheduler_token.encode(), configured_token.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid scheduler credentials",
        )


def get_internal_service_tenant(
    x_avenqo_tenant_id: UUID = Header(...),
    _: None = Depends(require_internal_service_token),
    db: Session = Depends(get_db),
) -> TenantContext:
    if db.get(Company, x_avenqo_tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantContext(company_id=x_avenqo_tenant_id)
