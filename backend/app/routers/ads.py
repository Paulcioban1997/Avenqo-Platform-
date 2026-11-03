"""FastAPI routes for Google Ads & Meta Ads integrations."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings, get_settings
from backend.app.connectors.ads.base import AdsConfigurationMissingError, AdsConnectorError
from backend.app.core.permissions import permissions_for
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.dependencies.commerce import ConnectorSecretCipher, get_connector_secret_cipher
from backend.app.dependencies.subscription import require_active_subscription
from backend.app.services.ads_service import AdsService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from shared.ai_engine.contracts import TenantContext

logger = logging.getLogger("avenqo.ads.routes")
router = APIRouter(prefix="/ads", tags=["Advertising Connectors"])


def get_ads_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    cipher: ConnectorSecretCipher = Depends(get_connector_secret_cipher),
) -> AdsService:
    return AdsService(db, settings, cipher)


def require_marketing_entitlement(
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> TenantContext:
    """Verifies that the tenant has an active Marketing module subscription."""
    tenant = TenantContext(company_id=identity.user.company_id, user_id=identity.user.id)
    if not ModuleEntitlementService(db).can_use_module(tenant, "marketing"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "MODULE_NOT_ENTITLED",
                "message": "Le module Marketing n'est pas actif pour cette entreprise.",
                "module": "marketing",
            },
        )
    return tenant


def require_marketing_read(
    identity: CurrentIdentity = Depends(get_current_identity),
) -> CurrentIdentity:
    """Read access: Requires marketing:read or data:read permission."""
    perms = permissions_for(identity.user.role)
    if "marketing:read" in perms or "data:read" in perms:
        return identity
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "INSUFFICIENT_ROLE",
            "message": "Permission 'marketing:read' requise pour consulter les canaux publicitaires.",
        },
    )


def require_marketing_connect(
    identity: CurrentIdentity = Depends(get_current_identity),
) -> CurrentIdentity:
    """Connect access: Requires marketing:connect permission (Owner, Admin, Manager)."""
    perms = permissions_for(identity.user.role)
    if "marketing:connect" in perms:
        return identity
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "INSUFFICIENT_ROLE",
            "message": "Permission 'marketing:connect' requise pour initier ou connecter un canal publicitaire.",
        },
    )


def require_marketing_disconnect(
    identity: CurrentIdentity = Depends(get_current_identity),
) -> CurrentIdentity:
    """Disconnect access: Requires marketing:disconnect permission (Owner, Admin only)."""
    perms = permissions_for(identity.user.role)
    if "marketing:disconnect" in perms:
        return identity
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "INSUFFICIENT_ROLE",
            "message": "Permission 'marketing:disconnect' requise pour déconnecter un canal publicitaire.",
        },
    )


def require_marketing_admin(
    identity: CurrentIdentity = Depends(get_current_identity),
) -> CurrentIdentity:
    """Admin access: Requires marketing:admin permission (Owner, Admin only)."""
    perms = permissions_for(identity.user.role)
    if "marketing:admin" in perms:
        return identity
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "INSUFFICIENT_ROLE",
            "message": "Permission 'marketing:admin' requise pour administrer les paramètres marketing.",
        },
    )


# Backward-compatible alias
require_marketing_write = require_marketing_connect


@router.get("/status")
async def get_ads_status(
    identity: CurrentIdentity = Depends(get_current_identity),
    _subscription: Any = Depends(require_active_subscription),
    _entitlement: TenantContext = Depends(require_marketing_entitlement),
    _read_guard: CurrentIdentity = Depends(require_marketing_read),
    service: AdsService = Depends(get_ads_service),
) -> dict[str, Any]:
    """Returns the configuration and connection status for Google Ads and Meta Ads."""
    statuses = service.get_status(identity.user.company_id)
    return {
        provider: {
            "provider": st.provider,
            "connected": st.connected,
            "configured": st.configured,
            "external_account_id": st.external_account_id,
            "account_name": st.account_name,
            "currency": st.currency,
            "status": st.status,
            "granted_scopes": st.granted_scopes,
            "last_successful_sync": st.last_successful_sync.isoformat() if st.last_successful_sync else None,
            "error_message": st.error_message,
            "setup_instructions": st.setup_instructions,
        }
        for provider, st in statuses.items()
    }


@router.get("/google/auth-url")
async def get_google_ads_auth_url(
    identity: CurrentIdentity = Depends(get_current_identity),
    _subscription: Any = Depends(require_active_subscription),
    _entitlement: TenantContext = Depends(require_marketing_entitlement),
    _connect_guard: CurrentIdentity = Depends(require_marketing_connect),
    service: AdsService = Depends(get_ads_service),
) -> dict[str, str]:
    """Generates a signed, single-use anti-replay OAuth authorization URL for Google Ads."""
    try:
        state = service.generate_oauth_state(identity.user.company_id, identity.user.id, "google_ads")
        auth_url = service.google_ads.get_auth_url(identity.user.company_id, identity.user.id, state)
        return {"auth_url": auth_url, "state": state}
    except AdsConfigurationMissingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": exc.message, "status": "BLOCKED"},
        )


@router.get("/google/callback")
async def google_ads_callback(
    code: str = Query(...),
    state: str = Query(...),
    customer_id: str | None = Query(None),
    service: AdsService = Depends(get_ads_service),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """OAuth callback endpoint for Google Ads."""
    frontend_base = settings.frontend_url or "https://avenqo.ca"
    try:
        company_id, user_id = service.verify_oauth_state(state, "google_ads")
        await service.connect_google_ads(company_id, code, customer_id)
        return RedirectResponse(f"{frontend_base}/marketing?google_ads=connected")
    except AdsConnectorError as exc:
        logger.warning("Google Ads callback failed: code=%s", exc.code)
        return RedirectResponse(f"{frontend_base}/marketing?google_ads=error&error_code={exc.code}")
    except Exception as exc:
        logger.error("Unexpected error during Google Ads callback", exc_info=True)
        return RedirectResponse(f"{frontend_base}/marketing?google_ads=error&error_code=OAUTH_CALLBACK_FAILED")


@router.post("/google/disconnect")
async def disconnect_google_ads(
    identity: CurrentIdentity = Depends(get_current_identity),
    _subscription: Any = Depends(require_active_subscription),
    _entitlement: TenantContext = Depends(require_marketing_entitlement),
    _disconnect_guard: CurrentIdentity = Depends(require_marketing_disconnect),
    service: AdsService = Depends(get_ads_service),
) -> dict[str, bool]:
    """Disconnects Google Ads integration."""
    success = service.disconnect(identity.user.company_id, "google_ads")
    return {"success": success}


@router.get("/google/campaigns")
async def get_google_ads_campaigns(
    period: str = Query("30d"),
    identity: CurrentIdentity = Depends(get_current_identity),
    _subscription: Any = Depends(require_active_subscription),
    _entitlement: TenantContext = Depends(require_marketing_entitlement),
    _read_guard: CurrentIdentity = Depends(require_marketing_read),
    service: AdsService = Depends(get_ads_service),
) -> list[dict[str, Any]]:
    """Lists Google Ads campaigns in read-only mode."""
    try:
        camps = await service.get_campaigns(identity.user.company_id, "google_ads", period)
        return [
            {
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "provider": c.provider,
                "currency_native": c.currency,
                "daily_budget_native": float(c.daily_budget_native) if c.daily_budget_native else None,
                "spend_native": float(c.spend_native),
                "spend_cad": float(c.spend_cad) if c.spend_cad is not None else None,
                "impressions": c.impressions,
                "clicks": c.clicks,
                "conversions": c.conversions,
                "ctr": c.ctr,
                "cpc_native": float(c.cpc_native),
                "roas": c.roas,
            }
            for c in camps
        ]
    except AdsConfigurationMissingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": exc.message, "status": "BLOCKED"},
        )


@router.get("/meta/auth-url")
async def get_meta_ads_auth_url(
    identity: CurrentIdentity = Depends(get_current_identity),
    _subscription: Any = Depends(require_active_subscription),
    _entitlement: TenantContext = Depends(require_marketing_entitlement),
    _connect_guard: CurrentIdentity = Depends(require_marketing_connect),
    service: AdsService = Depends(get_ads_service),
) -> dict[str, str]:
    """Generates a signed, single-use anti-replay OAuth authorization URL for Meta Ads."""
    try:
        state = service.generate_oauth_state(identity.user.company_id, identity.user.id, "meta_ads")
        auth_url = service.meta_ads.get_auth_url(identity.user.company_id, identity.user.id, state)
        return {"auth_url": auth_url, "state": state}
    except AdsConfigurationMissingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": exc.message, "status": "BLOCKED"},
        )


@router.get("/meta/callback")
async def meta_ads_callback(
    code: str = Query(...),
    state: str = Query(...),
    ad_account_id: str | None = Query(None),
    service: AdsService = Depends(get_ads_service),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """OAuth callback endpoint for Meta Ads."""
    frontend_base = settings.frontend_url or "https://avenqo.ca"
    try:
        company_id, user_id = service.verify_oauth_state(state, "meta_ads")
        await service.connect_meta_ads(company_id, code, ad_account_id)
        return RedirectResponse(f"{frontend_base}/marketing?meta_ads=connected")
    except AdsConnectorError as exc:
        logger.warning("Meta Ads callback failed: code=%s", exc.code)
        return RedirectResponse(f"{frontend_base}/marketing?meta_ads=error&error_code={exc.code}")
    except Exception as exc:
        logger.error("Unexpected error during Meta Ads callback", exc_info=True)
        return RedirectResponse(f"{frontend_base}/marketing?meta_ads=error&error_code=OAUTH_CALLBACK_FAILED")


@router.post("/meta/disconnect")
async def disconnect_meta_ads(
    identity: CurrentIdentity = Depends(get_current_identity),
    _subscription: Any = Depends(require_active_subscription),
    _entitlement: TenantContext = Depends(require_marketing_entitlement),
    _disconnect_guard: CurrentIdentity = Depends(require_marketing_disconnect),
    service: AdsService = Depends(get_ads_service),
) -> dict[str, bool]:
    """Disconnects Meta Ads integration."""
    success = service.disconnect(identity.user.company_id, "meta_ads")
    return {"success": success}


@router.get("/meta/campaigns")
async def get_meta_ads_campaigns(
    period: str = Query("30d"),
    identity: CurrentIdentity = Depends(get_current_identity),
    _subscription: Any = Depends(require_active_subscription),
    _entitlement: TenantContext = Depends(require_marketing_entitlement),
    _read_guard: CurrentIdentity = Depends(require_marketing_read),
    service: AdsService = Depends(get_ads_service),
) -> list[dict[str, Any]]:
    """Lists Meta Ads campaigns in read-only mode."""
    try:
        camps = await service.get_campaigns(identity.user.company_id, "meta_ads", period)
        return [
            {
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "provider": c.provider,
                "currency_native": c.currency,
                "daily_budget_native": float(c.daily_budget_native) if c.daily_budget_native else None,
                "lifetime_budget_native": float(c.lifetime_budget_native) if c.lifetime_budget_native else None,
                "spend_native": float(c.spend_native),
                "spend_cad": float(c.spend_cad) if c.spend_cad is not None else None,
                "impressions": c.impressions,
                "clicks": c.clicks,
                "conversions": c.conversions,
                "ctr": c.ctr,
                "cpc_native": float(c.cpc_native),
                "roas": c.roas,
            }
            for c in camps
        ]
    except AdsConfigurationMissingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": exc.message, "status": "BLOCKED"},
        )


@router.get("/performance/summary")
async def get_ads_performance_summary(
    period: str = Query("last_30d"),
    identity: CurrentIdentity = Depends(get_current_identity),
    _subscription: Any = Depends(require_active_subscription),
    _entitlement: TenantContext = Depends(require_marketing_entitlement),
    _read_guard: CurrentIdentity = Depends(require_marketing_read),
    service: AdsService = Depends(get_ads_service),
) -> dict[str, Any]:
    """Aggregated marketing performance across all connected advertising platforms."""
    return await service.get_combined_performance(identity.user.company_id, period)
