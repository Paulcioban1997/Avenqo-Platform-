"""FastAPI routes for Google Ads & Meta Ads integrations."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings, get_settings
from backend.app.connectors.ads.base import AdsConfigurationMissingError, AdsConnectorError
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity
from backend.app.dependencies.commerce import get_connector_secret_cipher
from backend.app.dependencies.subscription import require_active_subscription
from backend.app.services.ads_service import AdsService

router = APIRouter(prefix="/ads", tags=["Advertising Connectors"])


def get_ads_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdsService:
    return AdsService(db, settings, get_connector_secret_cipher())


@router.get("/status")
async def get_ads_status(
    identity: CurrentIdentity = Depends(get_current_identity),
    _subscription: Any = Depends(require_active_subscription),
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
    service: AdsService = Depends(get_ads_service),
) -> dict[str, str]:
    """Generates a signed OAuth authorization URL for Google Ads."""
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
        company_id, _ = service.verify_oauth_state(state, "google_ads")
        await service.connect_google_ads(company_id, code, customer_id)
        return RedirectResponse(f"{frontend_base}/marketing?google_ads=connected")
    except Exception as exc:
        err_msg = str(exc)
        return RedirectResponse(f"{frontend_base}/marketing?google_ads=error&error={err_msg}")


@router.post("/google/disconnect")
async def disconnect_google_ads(
    identity: CurrentIdentity = Depends(get_current_identity),
    _subscription: Any = Depends(require_active_subscription),
    service: AdsService = Depends(get_ads_service),
) -> dict[str, bool]:
    """Disconnects Google Ads integration."""
    success = service.disconnect(identity.user.company_id, "google_ads")
    return {"success": success}


@router.get("/google/campaigns")
async def get_google_ads_campaigns(
    identity: CurrentIdentity = Depends(get_current_identity),
    _subscription: Any = Depends(require_active_subscription),
    service: AdsService = Depends(get_ads_service),
) -> list[dict[str, Any]]:
    """Lists Google Ads campaigns in read-only mode."""
    try:
        camps = await service.get_campaigns(identity.user.company_id, "google_ads")
        return [
            {
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "provider": c.provider,
                "daily_budget_cad": float(c.daily_budget_cad) if c.daily_budget_cad else None,
                "spend_cad": float(c.spend_cad),
                "impressions": c.impressions,
                "clicks": c.clicks,
                "conversions": c.conversions,
                "ctr": c.ctr,
                "cpc_cad": float(c.cpc_cad),
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
    service: AdsService = Depends(get_ads_service),
) -> dict[str, str]:
    """Generates a signed OAuth authorization URL for Meta Ads."""
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
        company_id, _ = service.verify_oauth_state(state, "meta_ads")
        await service.connect_meta_ads(company_id, code, ad_account_id)
        return RedirectResponse(f"{frontend_base}/marketing?meta_ads=connected")
    except Exception as exc:
        err_msg = str(exc)
        return RedirectResponse(f"{frontend_base}/marketing?meta_ads=error&error={err_msg}")


@router.post("/meta/disconnect")
async def disconnect_meta_ads(
    identity: CurrentIdentity = Depends(get_current_identity),
    _subscription: Any = Depends(require_active_subscription),
    service: AdsService = Depends(get_ads_service),
) -> dict[str, bool]:
    """Disconnects Meta Ads integration."""
    success = service.disconnect(identity.user.company_id, "meta_ads")
    return {"success": success}


@router.get("/meta/campaigns")
async def get_meta_ads_campaigns(
    identity: CurrentIdentity = Depends(get_current_identity),
    _subscription: Any = Depends(require_active_subscription),
    service: AdsService = Depends(get_ads_service),
) -> list[dict[str, Any]]:
    """Lists Meta Ads campaigns in read-only mode."""
    try:
        camps = await service.get_campaigns(identity.user.company_id, "meta_ads")
        return [
            {
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "provider": c.provider,
                "daily_budget_cad": float(c.daily_budget_cad) if c.daily_budget_cad else None,
                "lifetime_budget_cad": float(c.lifetime_budget_cad) if c.lifetime_budget_cad else None,
                "spend_cad": float(c.spend_cad),
                "impressions": c.impressions,
                "clicks": c.clicks,
                "conversions": c.conversions,
                "ctr": c.ctr,
                "cpc_cad": float(c.cpc_cad),
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
    service: AdsService = Depends(get_ads_service),
) -> dict[str, Any]:
    """Aggregated marketing performance across all connected advertising platforms."""
    return await service.get_combined_performance(identity.user.company_id, period)

