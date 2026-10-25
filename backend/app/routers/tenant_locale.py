"""Authenticated, company-scoped linguistic profile API.

GET/PUT /api/v1/company/locale-profile is bound to the JWT tenant. A mismatched
company_id query/body never reveals another tenant's profile (404).
"""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.models.base import UserRole
from backend.app.schemas.tenant_locale import (
    LocaleCapability,
    LocaleSuggestionResponse,
    TenantLocaleProfileResponse,
    TenantLocaleProfileUpdate,
)
from backend.app.services.tenant_locale_service import (
    CATALOG_SIZE,
    FALLBACK_POLICY_MEANING,
    PROFILE_NOTE,
    LocaleNotInCatalog,
    TenantLocaleIsolationError,
    TenantLocaleProfileView,
    capabilities_for,
    get_profile,
    suggest_primary,
    upsert_profile,
)
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/company", tags=["tenant-locale"])
_PROFILE_EDITORS = frozenset({UserRole.OWNER, UserRole.ADMIN})


def _assert_same_tenant(
    tenant: TenantContext,
    identity: CurrentIdentity,
    company_id: UUID | None,
) -> None:
    if tenant.company_id != identity.user.company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Contexte tenant invalide")
    if company_id is not None and company_id != tenant.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profil linguistique introuvable")


def _to_response(view: TenantLocaleProfileView) -> TenantLocaleProfileResponse:
    return TenantLocaleProfileResponse(
        company_id=view.company_id,
        primary_locale=view.primary_locale,
        secondary_locales=list(view.secondary_locales),
        authorized_locales=list(view.authorized_locales),
        voice_by_locale=dict(view.voice_by_locale),
        fallback_policy=view.fallback_policy,
        fallback_policy_meaning=FALLBACK_POLICY_MEANING,
        suggested_locale=view.suggested_locale,
        suggested_secondaries=list(view.suggested_secondaries),
        persisted=view.persisted,
        timezone=view.timezone,
        timezone_source="company.timezone",
        catalog_size=CATALOG_SIZE,
        locales=[LocaleCapability(**asdict(cap)) for cap in view.locales],
        note=PROFILE_NOTE,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


@router.get("/locale-profile", response_model=TenantLocaleProfileResponse)
def read_locale_profile(
    company_id: UUID | None = Query(default=None),
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> TenantLocaleProfileResponse:
    _assert_same_tenant(tenant, identity, company_id)
    try:
        return _to_response(get_profile(db, tenant.company_id))
    except TenantLocaleIsolationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profil linguistique introuvable") from exc


@router.put("/locale-profile", response_model=TenantLocaleProfileResponse)
def write_locale_profile(
    payload: TenantLocaleProfileUpdate,
    company_id: UUID | None = Query(default=None),
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> TenantLocaleProfileResponse:
    _assert_same_tenant(tenant, identity, company_id)
    if identity.user.role not in _PROFILE_EDITORS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission insuffisante")
    try:
        view = upsert_profile(
            db,
            tenant.company_id,
            primary_locale=payload.primary_locale,
            secondary_locales=payload.secondary_locales,
            voice_by_locale=payload.voice_by_locale,
            fallback_policy=payload.fallback_policy,
        )
        db.commit()
        return _to_response(view)
    except LocaleNotInCatalog as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except TenantLocaleIsolationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profil linguistique introuvable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/locale-profile/suggestions", response_model=LocaleSuggestionResponse)
def suggest_locale_profile(
    country: str | None = Query(default=None),
    region: str | None = Query(default=None),
    timezone: str | None = Query(default=None),
    company_id: UUID | None = Query(default=None),
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
) -> LocaleSuggestionResponse:
    _assert_same_tenant(tenant, identity, company_id)
    # Suggestions are computed only. They must not write a profile row.
    before = get_profile(db, tenant.company_id)
    suggested, recommended = suggest_primary(country, region, timezone)
    after = get_profile(db, tenant.company_id)
    if after.persisted != before.persisted or after.primary_locale != before.primary_locale:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Suggestion must not persist")
    codes = [code for code in [suggested, *recommended] if code]
    return LocaleSuggestionResponse(
        country=country,
        region=region,
        timezone=timezone,
        suggested_primary=suggested,
        recommended_secondaries=recommended,
        applied=False,
        persisted=False,
        note="Suggestion only. The company must PUT an explicit primary_locale to persist a choice.",
        locales=[LocaleCapability(**asdict(cap)) for cap in capabilities_for(codes)],
    )
