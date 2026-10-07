"""Tenant-secured inbound voice agent, Telnyx webhooks, and Retell tools."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from math import isfinite
from httpx import HTTPStatusError, TimeoutException
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings, get_settings
from backend.app.core.rate_limit import rate_limit
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, require_permission
from backend.app.dependencies.subscription import require_active_subscription
from backend.app.dependencies.tenant_business import get_tenant_analytics_service
from backend.app.models import (
    BillingAccount,
    Company,
    CompanyMembership,
    TenantAIProviderAttempt,
    User,
    VoiceBusinessConfig,
    VoiceCall,
    VoiceCentralSession,
    VoicePhoneNumber,
    VoiceToolAction,
)
from backend.app.ai.chat.conversation_service import ConversationService
from backend.app.ai.tools.business.registry_factory import resolve_tenant_capabilities
from backend.app.dependencies.ai_engine import get_prediction_service
from backend.app.dependencies.central_ai import get_central_ai_service
from backend.app.ai.central.service import CentralAIService
from backend.app.core.locale_catalog import resolve_locale, detect_spoken_language
from backend.app.dependencies.ai_authorization import get_active_ai_membership
from backend.app.voice.languages import voice_language_matrix
from backend.app.voice.auth import VoiceCallerAuth, redact_voice_secrets
from backend.app.voice.quotes import signed_number_quote, verify_number_quote, valid_cost
from backend.app.voice.telnyx_media import telnyx_media_socket, media_audio_available, issue_media_client_state
from backend.app.schemas.voice import VoicePinRequest
from backend.app.schemas.voice import VoiceSetupRequest, VoiceOwnedNumberRequest
from backend.app.services.audit_log_service import AuditLogService
from backend.app.voice.service import voice_action_key
from backend.app.core.permissions import permissions_for
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.schemas.voice import (
    VoiceConfigCreatedResponse,
    VoiceConfigRequest,
    VoiceConfigResponse,
    VoiceNumberProvisionRequest,
    VoiceNumberReleaseRequest,
    VoiceNumberAssignRequest,
    VoiceToolRequest,
)
from backend.app.voice.providers import RetellVoiceProvider, TelnyxClient
from backend.app.voice.service import VoiceOrchestrator, _api_key_hash, resolve_voice_source_context
from backend.app.services.voice_number_service import (
    PhoneNumberSearch,
    VoiceNumberManagementService,
    VoiceNumberOwnerActionRequired,
)
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from backend.app.services.data_freshness_service import DataFreshnessService
from backend.app.models import CRMCalendarConnection
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/voice", tags=["voice-agent"])
router.add_api_websocket_route("/telnyx/media/{call_id}", telnyx_media_socket)
manage_voice = require_permission("modules:manage")
logger = logging.getLogger("avenqo.voice")


@router.post("/setup", dependencies=[Depends(require_active_subscription)])
async def setup_tenant_voice(
    request: VoiceSetupRequest,
    identity: CurrentIdentity = Depends(manage_voice),
    membership=Depends(get_active_ai_membership),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _ensure_voice_access(db, identity.user.company_id)
    if "modules:manage" not in permissions_for(membership.role):
        raise HTTPException(status_code=403, detail="Module management permission is required")
    if not request.confirmed:
        return {"status": "READY_FOR_OWNER_ACTION", "reason": "explicit_setup_confirmation_required"}
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"voice_setup:{identity.user.company_id}"})
    number = db.scalar(select(VoicePhoneNumber).where(VoicePhoneNumber.id == request.number_id,
        VoicePhoneNumber.company_id == identity.user.company_id, VoicePhoneNumber.status == "ACTIVE"))
    if number is None:
        raise HTTPException(status_code=404, detail="Active tenant number not found")
    service = _orchestrator(db, settings)
    existing = service.config_for_tenant(TenantContext(identity.user.company_id))
    if existing is not None:
        if existing.telnyx_phone_number != number.phone_number or number.config_id not in {None, existing.id}:
            raise HTTPException(status_code=409, detail="Existing Voice configuration conflicts with this number")
        if number.config_id is None:
            number.config_id = existing.id; db.commit()
        return {"status": "CONFIGURED" if existing.enabled else "AUDIO_CONFIGURATION_REQUIRED", "configuration": _config_response(existing).model_dump(mode="json")}
    company = identity.user.company
    values = VoiceConfigRequest(business_name=company.name, timezone_name=company.timezone or "UTC",
        preferred_language=company.preferred_language or "fr", telnyx_phone_number=number.phone_number,
        opening_hours={}, services=[], enabled=False).model_dump(mode="json")
    try:
        config, _one_time_secret = await service.upsert_config(TenantContext(company.id, identity.user.id), values)
    except IntegrityError:
        db.rollback()
        existing = service.config_for_tenant(TenantContext(company.id))
        if existing is None or existing.telnyx_phone_number != number.phone_number:
            raise HTTPException(status_code=409, detail="Voice configuration changed; reload setup") from None
        return {"status": "AUDIO_CONFIGURATION_REQUIRED", "configuration": _config_response(existing).model_dump(mode="json")}
    AuditLogService(db).record(actor_user_id=identity.user.id, action="voice_setup_created", target_type="voice_configuration",
        target_id=str(config.id), company_id=company.id, metadata={"audio_provider_configured": False})
    return {"status": "AUDIO_CONFIGURATION_REQUIRED", "configuration": _config_response(config).model_dump(mode="json")}


@router.post("/numbers/import", dependencies=[Depends(require_active_subscription), Depends(rate_limit("voice_number_import", "rate_limit_ai_per_minute"))])
async def import_owned_voice_number(
    request: VoiceOwnedNumberRequest,
    identity: CurrentIdentity = Depends(manage_voice),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _ensure_voice_access(db, identity.user.company_id)
    try:
        number = await _voice_number_service(settings).register_owned_number(db,
            TenantContext(identity.user.company_id, identity.user.id), request.phone_number, confirmed=request.confirmed)
        db.commit(); db.refresh(number)
        return {"status": "ACTIVE", "number": _voice_number_response(number)}
    except (ValueError, PermissionError):
        db.rollback()
        raise HTTPException(status_code=409, detail="Owned number cannot be imported in this tenant state") from None


@router.put("/auth/pin", dependencies=[Depends(require_active_subscription), Depends(rate_limit("voice_pin_setup", "rate_limit_ai_per_minute"))])
def set_user_voice_pin(
    request: VoicePinRequest,
    identity: CurrentIdentity = Depends(get_current_identity),
    membership=Depends(get_active_ai_membership),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _ensure_voice_access(db, identity.user.company_id)
    if "ai:use" not in permissions_for(membership.role):
        raise HTTPException(status_code=403, detail="AI permission is required")
    try:
        VoiceCallerAuth(db, settings).set_pin(TenantContext(identity.user.company_id, identity.user.id),
            "USER", identity.user.id, request.pin.get_secret_value())
        AuditLogService(db).record(actor_user_id=identity.user.id, action="voice_pin_updated", target_type="user",
            target_id=str(identity.user.id), company_id=identity.user.company_id, metadata={"credential_type": "USER"}, commit=False)
        db.commit()
    except (ValueError, PermissionError):
        db.rollback()
        raise HTTPException(status_code=422, detail="Voice credential setup is unavailable") from None
    return {"status": "CONFIGURED"}


@router.put("/auth/customers/{customer_id}/pin", dependencies=[Depends(require_active_subscription), Depends(rate_limit("voice_customer_pin_setup", "rate_limit_ai_per_minute"))])
def set_customer_voice_pin(
    customer_id: UUID,
    request: VoicePinRequest,
    identity: CurrentIdentity = Depends(manage_voice),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _ensure_voice_access(db, identity.user.company_id)
    try:
        VoiceCallerAuth(db, settings).set_pin(TenantContext(identity.user.company_id, identity.user.id),
            "CUSTOMER", customer_id, request.pin.get_secret_value())
        AuditLogService(db).record(actor_user_id=identity.user.id, action="voice_customer_pin_updated", target_type="crm_client",
            target_id=str(customer_id), company_id=identity.user.company_id, metadata={"credential_type": "CUSTOMER"}, commit=False)
        db.commit()
    except (ValueError, PermissionError):
        db.rollback()
        raise HTTPException(status_code=422, detail="Voice credential setup is unavailable") from None
    return {"status": "CONFIGURED"}


@router.get("/capabilities", dependencies=[Depends(require_active_subscription)])
def get_voice_capabilities(
    identity: CurrentIdentity = Depends(get_current_identity),
    membership=Depends(get_active_ai_membership),
    central_ai: CentralAIService = Depends(get_central_ai_service),
) -> dict[str, Any]:
    company = identity.user.company
    permissions = frozenset(permissions_for(membership.role))
    if "ai:use" not in permissions:
        raise HTTPException(status_code=403, detail="AI permission is required")
    context = central_ai.capability_context(
        TenantContext(company_id=company.id, user_id=identity.user.id), identity.user.id,
        permissions=permissions,
        user_language=resolve_locale(company.preferred_language or "fr"),
        company_country=company.country or "",
        company_currency=company.currency_code,
        company_timezone=company.timezone or "UTC",
    )
    return {**context.as_capabilities(), "language_matrix": voice_language_matrix()}


def _orchestrator(db: Session, settings: Settings) -> VoiceOrchestrator:
    return VoiceOrchestrator(db, settings, RetellVoiceProvider(settings), TelnyxClient(settings))


def _config_response(config: VoiceBusinessConfig) -> VoiceConfigResponse:
    return VoiceConfigResponse.model_validate(VoiceOrchestrator.public_config(config))


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@router.get("/status", dependencies=[Depends(require_active_subscription)])
def get_voice_status(
    identity: CurrentIdentity = Depends(manage_voice),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    analytics: TenantAnalyticsService = Depends(get_tenant_analytics_service),
) -> dict[str, Any]:
    company_id = identity.user.company_id
    voice_module_active = ModuleEntitlementService(db).can_use_module(TenantContext(company_id), "voice")
    config = VoiceOrchestrator(db, settings).config_for_tenant(TenantContext(company_id))
    active_number = db.scalar(select(VoicePhoneNumber).where(
        VoicePhoneNumber.company_id == company_id,
        VoicePhoneNumber.status == "ACTIVE",
        VoicePhoneNumber.config_id == (config.id if config is not None else None),
    )) if config is not None else db.scalar(select(VoicePhoneNumber).where(
        VoicePhoneNumber.company_id == company_id,
        VoicePhoneNumber.status == "ACTIVE",
        VoicePhoneNumber.config_id.is_(None),
    ))
    snapshot = analytics.load(TenantContext(company_id, identity.user.id))
    calendar_connected = db.scalar(select(CRMCalendarConnection.id).where(
        CRMCalendarConnection.company_id == company_id,
        CRMCalendarConnection.sync_status == "connected",
    ).limit(1)) is not None
    calls = db.scalars(select(VoiceCall).where(VoiceCall.company_id == company_id)).all()
    call_minutes = round(sum(
        max(0.0, (
            _as_utc(call.ended_at or datetime.now(timezone.utc))
            - _as_utc(call.started_at or datetime.now(timezone.utc))
        ).total_seconds())
        for call in calls
    ) / 60, 2)
    session_ids = {
        item.conversation_id
        for item in db.scalars(select(VoiceCentralSession).where(VoiceCentralSession.company_id == company_id)).all()
    }
    session_ids.update(call.central_conversation_id for call in calls if call.central_conversation_id is not None)
    voice_attempts = db.scalars(select(TenantAIProviderAttempt).where(
        TenantAIProviderAttempt.company_id == company_id,
        TenantAIProviderAttempt.conversation_id.in_(session_ids),
    )).all() if session_ids else []
    voice_ai_credits = sum(int(item.avenqo_credits_charged or 0) for item in voice_attempts)
    telnyx_configured = bool(settings.telnyx_api_key and settings.telnyx_public_key and settings.telnyx_voice_connection_id)
    return {
        "voice_status": "ENABLED" if config is not None and config.enabled else "DISABLED" if config is not None else "NOT_CONFIGURED",
        "module_entitled": voice_module_active,
        "number_status": active_number.status if active_number is not None else "READY_FOR_OWNER_ACTION" if not telnyx_configured else "NO_NUMBER_ASSIGNED",
        "business_number": active_number.phone_number if active_number is not None else config.telnyx_phone_number if config is not None else None,
        "number_id": str(active_number.id) if active_number is not None else None,
        "configuration_status": "AUDIO_READY" if config is not None and config.enabled else "AUDIO_CONFIGURATION_REQUIRED" if config is not None else "NOT_CONFIGURED",
        "country": active_number.country_code if active_number is not None else None,
        "region": active_number.region if active_number is not None else None,
        "locality": active_number.locality if active_number is not None else None,
        "provider": active_number.provider if active_number is not None else "telnyx" if telnyx_configured else None,
        "voice_capability": "voice" in (active_number.capabilities or []) if active_number is not None else False,
        "sms_capability": "sms" in (active_number.capabilities or []) if active_number is not None else False,
        "telnyx_status": "CONFIGURED" if telnyx_configured else "NOT_CONFIGURED",
        "retell_status": "CONFIGURED" if settings.retell_api_key else "NOT_CONFIGURED",
        "stt_status": "CONFIGURED" if settings.voice_stt_provider and settings.openai_api_key else "NOT_CONFIGURED",
        "tts_status": "CONFIGURED" if settings.voice_tts_provider and settings.openai_api_key else "NOT_CONFIGURED",
        "realtime_status": "CONFIGURED" if settings.voice_realtime_provider and settings.voice_realtime_model and settings.openai_api_key and settings.voice_realtime_supported_locales else "NOT_CONFIGURED",
        "realtime_supported_locales": sorted(settings.voice_realtime_supported_locales),
        "preferred_language": config.preferred_language if config is not None else identity.user.company.preferred_language,
        "auto_language_detection": True,
        "crm_status": "CONFIGURED",
        "calendar_status": "CONNECTED" if calendar_connected else "NOT_CONNECTED",
        "retail_source_context": {
            "selection": snapshot.active_source_type,
            "provider": snapshot.active_source_provider,
            "name": snapshot.active_source_name,
        },
        "data_freshness": DataFreshnessService().for_snapshot(snapshot).as_dict(),
        "authorized_members_count": int(db.scalar(select(func.count(CompanyMembership.id)).where(
            CompanyMembership.company_id == company_id,
            CompanyMembership.is_active.is_(True),
        )) or 0),
        "call_count": len(calls),
        "recent_calls": [{
            "id": str(call.id),
            "status": call.status,
            "started_at": _as_utc(call.started_at).isoformat() if call.started_at else None,
            "ended_at": _as_utc(call.ended_at).isoformat() if call.ended_at else None,
        } for call in sorted(calls, key=lambda item: _as_utc(item.started_at) if item.started_at else datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:20]],
        "call_minutes": call_minutes,
        "voice_ai_credits_charged": voice_ai_credits,
    }


def _voice_number_service(settings: Settings) -> VoiceNumberManagementService:
    return VoiceNumberManagementService(TelnyxClient(settings))


def _voice_number_response(number: VoicePhoneNumber) -> dict[str, Any]:
    return {
        "id": str(number.id),
        "phone_number": number.phone_number,
        "country_code": number.country_code,
        "region": number.region,
        "locality": number.locality,
        "provider": number.provider,
        "number_type": number.number_type,
        "capabilities": number.capabilities,
        "regulatory_status": number.regulatory_status,
        "regulatory_requirements": number.regulatory_requirements,
        "monthly_cost": float(number.monthly_cost) if number.monthly_cost is not None else None,
        "monthly_cost_currency": number.monthly_cost_currency,
        "status": number.status,
        "purchased_at": number.purchased_at,
        "released_at": number.released_at,
        "assigned": number.config_id is not None,
    }


@router.get(
    "/numbers/search",
    dependencies=[Depends(require_active_subscription), Depends(rate_limit("voice_number_search", "rate_limit_ai_per_minute"))],
)
async def search_voice_numbers(
    country_code: str,
    region: str | None = None,
    locality: str | None = None,
    number_type: str | None = None,
    limit: int = 20,
    area_code: str | None = None,
    prefix: str | None = None,
    capabilities: list[str] = Query(default=["voice"]),
    offset: int = 0,
    identity: CurrentIdentity = Depends(manage_voice),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _ensure_voice_access(db, identity.user.company_id)
    try:
        return await _voice_number_service(settings).search(
            PhoneNumberSearch(country_code, region, locality, number_type, limit, area_code, prefix, tuple(capabilities), offset)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Telnyx number search is not configured") from exc
    except TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Voice number search timed out") from exc
    except HTTPStatusError as exc:
        if exc.response.status_code in {400, 422}:
            raise HTTPException(status_code=422, detail="Telnyx rejected the search filters") from exc
        raise HTTPException(status_code=502, detail="Voice number search provider is unavailable") from exc
    except Exception as exc:
        logger.warning("Telnyx number search failed", extra={"company_id": str(identity.user.company_id)})
        raise HTTPException(status_code=502, detail="Voice number search is temporarily unavailable") from exc


@router.get("/numbers/quote", dependencies=[Depends(require_active_subscription), Depends(rate_limit("voice_number_quote", "rate_limit_ai_per_minute"))])
async def quote_voice_number(
    phone_number: str,
    country_code: str,
    number_type: str | None = None,
    region: str | None = None,
    locality: str | None = None,
    identity: CurrentIdentity = Depends(manage_voice),
    membership=Depends(get_active_ai_membership),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _ensure_voice_access(db, identity.user.company_id)
    if "modules:manage" not in permissions_for(membership.role):
        raise HTTPException(status_code=403, detail="Module management permission is required")
    try:
        search = await _voice_number_service(settings).search(PhoneNumberSearch(country_code, region, locality, number_type, 100))
        offer = next((item for item in search["offers"] if item["phone_number"] == phone_number), None)
        if offer is None:
            raise HTTPException(status_code=409, detail="The selected number is not currently available")
        try:
            regulatory = await TelnyxClient(settings).number_requirements(phone_number, country_code.upper(), offer["number_type"])
        except Exception:
            regulatory = {"status": "unknown", "requirements": []}
        offer.update(regulatory_status=regulatory["status"], regulatory_requirements=regulatory["requirements"])
        token = signed_number_quote(settings, identity.user.company_id, identity.user.id, offer)
        return {"offer": offer, "quote_token": token, "expires_in_seconds": 300,
            "purchase_allowed": regulatory["status"] == "verified_no_requirements"}
    except HTTPException:
        raise
    except (ValueError, RuntimeError, TimeoutException, HTTPStatusError):
        raise HTTPException(status_code=422, detail="A complete provider number quote is unavailable") from None
    except Exception:
        logger.warning("Telnyx number quote failed", extra={"company_id": str(identity.user.company_id)})
        raise HTTPException(status_code=502, detail="Voice number quote is temporarily unavailable") from None


@router.post(
    "/numbers/provision",
    dependencies=[Depends(require_active_subscription), Depends(rate_limit("voice_number_provision", "rate_limit_ai_per_minute"))],
)
async def provision_voice_number(
    request: VoiceNumberProvisionRequest,
    identity: CurrentIdentity = Depends(manage_voice),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    membership=Depends(get_active_ai_membership),
) -> dict[str, Any]:
    company_id = identity.user.company_id
    _ensure_voice_access(db, company_id)
    if "modules:manage" not in permissions_for(membership.role):
        raise HTTPException(status_code=403, detail="Module management permission is required")
    existing = db.scalar(select(VoicePhoneNumber).where(VoicePhoneNumber.phone_number == request.phone_number))
    if existing is not None:
        if existing.company_id != company_id:
            raise HTTPException(status_code=409, detail="This number is assigned to another tenant")
        state = "ALREADY_ASSIGNED" if existing.status == "ACTIVE" else "READY_FOR_OWNER_ACTION"
        return {"status": state, "number": _voice_number_response(existing)}
    if not request.confirmed:
        return {"status": "READY_FOR_OWNER_ACTION", "reason": "explicit_purchase_confirmation_required"}
    if not settings.telnyx_voice_connection_id:
        return {"status": "READY_FOR_OWNER_ACTION", "reason": "TELNYX_VOICE_CONNECTION_ID_required"}
    try:
        quote = verify_number_quote(settings, request.quote_token, company_id, identity.user.id, request.phone_number)
    except (ValueError, PermissionError):
        raise HTTPException(status_code=409, detail="A current tenant-owned confirmed quote is required") from None
    if quote.get("regulatory_status") != "verified_no_requirements":
        return {"status": "READY_FOR_OWNER_ACTION", "reason": "regulatory_verification_required_no_order_placed"}
    manager = _voice_number_service(settings)
    reservation = None
    try:
        search = await manager.search(PhoneNumberSearch(
            request.country_code, request.region, request.locality, request.number_type, 100
        ))
        offer = next((item for item in search["offers"] if item["phone_number"] == request.phone_number), None)
        if offer is None:
            raise HTTPException(status_code=409, detail="The selected number is no longer available")
        costs = offer.get("cost_information") or {}
        if quote["country_code"] != request.country_code.upper() or quote["number_type"] != offer["number_type"] or quote["currency"] != str(costs.get("currency") or "").upper() or quote["monthly_cost"] != valid_cost(costs.get("monthly_cost")) or quote["upfront_cost"] != valid_cost(costs.get("upfront_cost")):
            raise HTTPException(status_code=409, detail="The provider quote changed; confirm a new quote")
        regulatory = await TelnyxClient(settings).number_requirements(request.phone_number, request.country_code.upper(), offer["number_type"])
        if regulatory["status"] != "verified_no_requirements":
            return {"status": "READY_FOR_OWNER_ACTION", "reason": "regulatory_verification_required_no_order_placed"}
        offer["regulatory_status"] = regulatory["status"]
        if offer.get("monthly_cost") is None:
            return {"status": "READY_FOR_OWNER_ACTION", "reason": "provider_price_unavailable_no_order_placed"}
        if offer.get("regulatory_requirements"):
            return {
                "status": "READY_FOR_OWNER_ACTION",
                "reason": "regulatory_documents_required_no_order_placed",
                "regulatory_requirements": offer["regulatory_requirements"],
            }
        reservation = VoicePhoneNumber(
            company_id=company_id,
            phone_number=offer["phone_number"],
            country_code=offer["country_code"],
            region=offer.get("region"),
            locality=offer.get("locality"),
            provider="telnyx",
            number_type=offer["number_type"],
            capabilities=[name for name in ("voice", "sms") if offer.get(f"{name}_capability")],
            regulatory_status=offer["regulatory_status"],
            regulatory_requirements=offer["regulatory_requirements"],
            status="ORDERING",
            monthly_cost=offer["monthly_cost"],
            monthly_cost_currency=offer["monthly_cost_currency"],
            upfront_cost=quote["upfront_cost"], provider_connection_id=settings.telnyx_voice_connection_id,
        )
        db.add(reservation)
        try:
            db.commit()
        except Exception:
            db.rollback()
            existing = db.scalar(select(VoicePhoneNumber).where(VoicePhoneNumber.phone_number == request.phone_number))
            if existing is not None:
                if existing.company_id != company_id:
                    raise HTTPException(status_code=409, detail="This number is assigned to another tenant")
                return {"status": "READY_FOR_OWNER_ACTION", "number": _voice_number_response(existing)}
            raise
        db.refresh(reservation)
        order = await manager.provision(
            offer=offer,
            confirmed=True,
            connection_id=settings.telnyx_voice_connection_id,
            messaging_profile_id=settings.telnyx_messaging_profile_id,
            idempotency_key=hashlib.sha256(f"{company_id}:{request.phone_number}".encode()).hexdigest(),
        )
    except HTTPException:
        raise
    except VoiceNumberOwnerActionRequired as exc:
        return {"status": "READY_FOR_OWNER_ACTION", "reason": str(exc)}
    except Exception as exc:
        if reservation is None:
            raise HTTPException(status_code=502, detail="Number offer verification is unavailable; no order placed") from None
        reservation.status = "OUTCOME_UNKNOWN"
        db.commit()
        logger.warning("Telnyx number order outcome requires reconciliation", extra={"company_id": str(company_id)})
        return {"status": "READY_FOR_OWNER_ACTION", "reason": "provider_order_outcome_unknown", "number": _voice_number_response(reservation)}

    order_data = order.get("data") if isinstance(order.get("data"), dict) else {}
    reservation.provider_order_id = str(order_data["id"]) if order_data.get("id") else None
    returned_numbers = order_data.get("phone_numbers") or []
    number_data = returned_numbers[0] if returned_numbers and isinstance(returned_numbers[0], dict) else {}
    provider_number_id = None
    order_status = str(number_data.get("status") or order_data.get("status") or "order_outcome_unknown").upper()
    reservation.provider_number_id = str(provider_number_id) if provider_number_id else None
    reservation.status = "VERIFYING" if order_status in {"SUCCESS", "ACTIVE", "COMPLETED"} else (
        "PENDING_REGULATORY" if reservation.regulatory_requirements else order_status
    )
    if reservation.status == "VERIFYING":
        try:
            owned = await TelnyxClient(settings).get_owned_number(request.phone_number)
            reservation.provider_number_id = str(owned["id"])
            reservation.status = "ACTIVE"
        except Exception:
            reservation.status = "VERIFYING"
    reservation.purchased_at = datetime.now(timezone.utc) if reservation.status == "ACTIVE" else None
    db.commit()
    db.refresh(reservation)
    return {"status": reservation.status, "number": _voice_number_response(reservation)}


@router.post(
    "/numbers/{number_id}/release",
    dependencies=[Depends(require_active_subscription), Depends(rate_limit("voice_number_release", "rate_limit_ai_per_minute"))],
)
async def release_voice_number(
    number_id: UUID,
    request: VoiceNumberReleaseRequest,
    identity: CurrentIdentity = Depends(manage_voice),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    company_id = identity.user.company_id
    _ensure_voice_access(db, company_id)
    number = db.scalar(select(VoicePhoneNumber).where(
        VoicePhoneNumber.id == number_id,
        VoicePhoneNumber.company_id == company_id,
    ))
    if number is None:
        raise HTTPException(status_code=404, detail="Voice number not found")
    if number.status == "RELEASED":
        return {"status": "RELEASED", "number": _voice_number_response(number)}
    if number.status != "ACTIVE":
        return {"status": "READY_FOR_OWNER_ACTION", "reason": "number_lifecycle_outcome_requires_reconciliation", "number": _voice_number_response(number)}
    if number.config_id is not None:
        raise HTTPException(status_code=409, detail="Unassign the active Voice configuration before release")
    if not request.confirmed:
        return {"status": "READY_FOR_OWNER_ACTION", "number": _voice_number_response(number)}
    if not number.provider_number_id:
        return {"status": "READY_FOR_OWNER_ACTION", "reason": "provider_number_id_missing_manual_reconciliation_required"}
    number.status = "RELEASING"
    db.commit()
    try:
        await _voice_number_service(settings).release(
            provider_number_id=number.provider_number_id,
            confirmed=True,
        )
    except Exception as exc:
        number.status = "RELEASE_OUTCOME_UNKNOWN"
        db.commit()
        logger.exception("Telnyx number release failed", extra={"company_id": str(company_id)})
        return {"status": "READY_FOR_OWNER_ACTION", "reason": "provider_release_outcome_unknown", "number": _voice_number_response(number)}
    number.status = "RELEASED"
    number.released_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(number)
    return {"status": "RELEASED", "number": _voice_number_response(number)}


@router.post(
    "/numbers/{number_id}/assign",
    dependencies=[Depends(require_active_subscription), Depends(rate_limit("voice_number_assign", "rate_limit_ai_per_minute"))],
)
def assign_voice_number(
    number_id: UUID,
    request: VoiceNumberAssignRequest,
    identity: CurrentIdentity = Depends(manage_voice),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    company_id = identity.user.company_id
    _ensure_voice_access(db, company_id)
    number = db.scalar(select(VoicePhoneNumber).where(
        VoicePhoneNumber.id == number_id,
        VoicePhoneNumber.company_id == company_id,
        VoicePhoneNumber.status == "ACTIVE",
    ))
    if number is None:
        raise HTTPException(status_code=404, detail="Active tenant voice number not found")
    if not request.confirmed:
        return {"status": "READY_FOR_OWNER_ACTION", "number": _voice_number_response(number)}
    config = _orchestrator(db, settings).config_for_tenant(TenantContext(company_id))
    if config is None:
        raise HTTPException(status_code=404, detail="Create the tenant Voice configuration before assigning a number")
    if number.config_id not in {None, config.id}:
        raise HTTPException(status_code=409, detail="Voice number is already assigned to another tenant configuration")
    config.telnyx_phone_number = number.phone_number
    number.config_id = config.id
    db.commit()
    db.refresh(number)
    return {"status": "ASSIGNED", "number": _voice_number_response(number)}


def _verify_telnyx_signature(request: Request, raw_body: bytes, settings: Settings) -> None:
    signature = request.headers.get("telnyx-signature-ed25519")
    timestamp = request.headers.get("telnyx-timestamp")
    if not signature or not timestamp or not settings.telnyx_public_key:
        raise HTTPException(status_code=401, detail="Telnyx webhook signature is not configured")
    try:
        timestamp_float = float(timestamp)
        if not isfinite(timestamp_float) or abs(time.time() - timestamp_float) > settings.telnyx_webhook_max_age_seconds:
            raise ValueError("expired signature")
        public_bytes = base64.b64decode(settings.telnyx_public_key, validate=True)
        signature_bytes = base64.b64decode(signature, validate=True)
        Ed25519PublicKey.from_public_bytes(public_bytes).verify(
            signature_bytes,
            timestamp.encode("ascii") + b"|" + raw_body,
        )
    except (ValueError, binascii.Error, InvalidSignature) as exc:
        raise HTTPException(status_code=401, detail="Invalid Telnyx webhook signature") from exc


def _authenticated_voice_config(
    db: Session,
    settings: Settings,
    api_key: str | None,
) -> tuple[VoiceBusinessConfig, VoiceOrchestrator]:
    service = _orchestrator(db, settings)
    config = service.config_from_api_key(api_key)
    if config is None:
        raise HTTPException(status_code=401, detail="Invalid tenant voice API key")
    _ensure_voice_access(db, config.company_id)
    return config, service


def _ensure_voice_access(db: Session, company_id: UUID) -> None:
    account = db.scalar(select(BillingAccount).where(BillingAccount.company_id == company_id))
    if account is None or account.status.strip().lower() not in {"active", "trialing"}:
        raise HTTPException(status_code=402, detail="An active subscription is required")
    if not ModuleEntitlementService(db).can_use_module(TenantContext(company_id), "voice"):
        raise HTTPException(status_code=403, detail="Voice module is not active for this tenant")


def _call_event_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    body = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    return data, body


@router.get("/config", response_model=VoiceConfigResponse, dependencies=[Depends(require_active_subscription)])
def get_voice_config(
    identity: CurrentIdentity = Depends(manage_voice),
    db: Session = Depends(get_db),
) -> VoiceConfigResponse:
    service = _orchestrator(db, get_settings())
    config = service.config_for_tenant(TenantContext(identity.user.company_id))
    if config is None:
        raise HTTPException(status_code=404, detail="Voice configuration not found")
    _ensure_voice_access(db, identity.user.company_id)
    return _config_response(config)


@router.post("/config", response_model=VoiceConfigCreatedResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_active_subscription)])
async def create_voice_config(
    request: VoiceConfigRequest,
    identity: CurrentIdentity = Depends(manage_voice),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> VoiceConfigCreatedResponse:
    service = _orchestrator(db, settings)
    try:
        config, api_key = await service.upsert_config(
            TenantContext(identity.user.company_id), request.model_dump(mode="json"), create_only=True
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return VoiceConfigCreatedResponse(**service.public_config(config), voice_api_key=api_key or "")


@router.put("/config", response_model=VoiceConfigResponse, dependencies=[Depends(require_active_subscription)])
async def update_voice_config(
    request: VoiceConfigRequest,
    identity: CurrentIdentity = Depends(manage_voice),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> VoiceConfigResponse:
    service = _orchestrator(db, settings)
    try:
        config, _ = await service.upsert_config(
            TenantContext(identity.user.company_id), request.model_dump(mode="json")
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _config_response(config)


@router.post("/config/rotate-key", response_model=VoiceConfigCreatedResponse,
             dependencies=[Depends(require_active_subscription)])
def rotate_voice_key(
    identity: CurrentIdentity = Depends(manage_voice),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> VoiceConfigCreatedResponse:
    service = _orchestrator(db, settings)
    try:
        _ensure_voice_access(db, identity.user.company_id)
        config, key = service.rotate_api_key(TenantContext(identity.user.company_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return VoiceConfigCreatedResponse(**service.public_config(config), voice_api_key=key)


@router.post("/telnyx/webhook", dependencies=[Depends(rate_limit("voice_telnyx_webhook", "rate_limit_webhook_per_minute"))])
async def telnyx_webhook(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    raw_body = await request.body()
    _verify_telnyx_signature(request, raw_body, settings)
    try:
        envelope = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook JSON") from exc
    if not isinstance(envelope, dict):
        raise HTTPException(status_code=400, detail="Invalid webhook envelope")
    data, call_payload = _call_event_data(envelope)
    event_type = str(data.get("event_type") or "")
    call_control_id = str(call_payload.get("call_control_id") or "")
    if event_type not in {"call.initiated", "call.answered", "call.bridged", "call.hangup", "call.gather.ended"}:
        return {"received": True, "handled": False}
    event_id = str(data.get("id") or "")
    if not event_id or len(event_id) > 255 or not call_control_id or len(call_control_id) > 255:
        raise HTTPException(status_code=422, detail="Telnyx event and call identifiers are required")
    if not settings.telnyx_voice_connection_id or str(call_payload.get("connection_id") or "") != settings.telnyx_voice_connection_id:
        return {"received": True, "routed": False}
    if event_type == "call.initiated" and call_payload.get("direction") != "incoming":
        return {"received": True, "routed": False}
    destination = str(call_payload.get("to") or "")
    binding = db.scalar(select(VoicePhoneNumber).where(
        VoicePhoneNumber.phone_number == destination,
        VoicePhoneNumber.provider == "telnyx",
        VoicePhoneNumber.status == "ACTIVE",
    ))
    if binding is None or binding.config_id is None or "voice" not in (binding.capabilities or []):
        return {"received": True, "routed": False}
    config = db.scalar(select(VoiceBusinessConfig).where(
        VoiceBusinessConfig.id == binding.config_id,
        VoiceBusinessConfig.company_id == binding.company_id,
        VoiceBusinessConfig.telnyx_phone_number == binding.phone_number,
    ))
    if config is None:
        return {"received": True, "routed": False}
    media_mode = settings.telnyx_media_enabled and settings.telnyx_media_inbound_enabled
    if not config.enabled and not media_mode:
        return {"received": True, "routed": False}
    if media_mode:
        from urllib.parse import urlsplit
        target_url = urlsplit(settings.telnyx_media_stream_base_url or "")
        if (target_url.scheme != "wss" or not target_url.hostname or target_url.username or target_url.password
            or target_url.query or target_url.fragment or binding.provider_connection_id != settings.telnyx_voice_connection_id
            or not media_audio_available(settings, config.preferred_language)):
            return {"received": True, "routed": False, "status": "READY_FOR_OWNER_ACTION"}
    service = _orchestrator(db, settings)
    try:
        _ensure_voice_access(db, config.company_id)
    except HTTPException:
        return {"received": True, "routed": False}
    event_key = hashlib.sha256(f"telnyx-event:{event_id}".encode("utf-8")).hexdigest()
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy import text
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"), {"lock_key": f"telnyx_event:{event_key}"})
    receipt = db.scalar(select(VoiceToolAction).where(
        VoiceToolAction.action_id == event_key, VoiceToolAction.tool_name == "telnyx_event",
    ))
    if receipt is not None:
        matching = (
            receipt.company_id == config.company_id and receipt.config_id == config.id
            and receipt.result.get("call_control_id") == call_control_id
            and receipt.result.get("event_type") == event_type
        )
        return {"received": True, "duplicate": True, "routed": matching and receipt.result.get("routed") is True}
    try:
        call = service.record_inbound(config, call_payload) if event_type == "call.initiated" else db.scalar(select(VoiceCall).where(
            VoiceCall.telnyx_call_control_id == call_control_id,
            VoiceCall.company_id == config.company_id,
            VoiceCall.config_id == config.id,
        ))
    except PermissionError:
        return {"received": True, "routed": False}
    if call is None:
        return {"received": True, "routed": False}
    if event_type == "call.initiated" and (call.ended_at is not None or call.status != "incoming"):
        return {"received": True, "routed": call.status in {"routing", "routed", "in_progress"}, "duplicate": True}
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"), {"lock_key": f"telnyx_event:{event_key}"})
        existing = db.scalar(select(VoiceToolAction).where(
            VoiceToolAction.action_id == event_key, VoiceToolAction.tool_name == "telnyx_event",
        ))
        if existing is not None:
            return {"received": True, "duplicate": True, "routed": False}
    receipt = VoiceToolAction(company_id=config.company_id, config_id=config.id, action_id=event_key,
        tool_name="telnyx_event", result={"event_type": event_type, "call_control_id": call_control_id, "routed": False})
    db.add(receipt)
    try:
        db.commit()
    except Exception:
        db.rollback()
        existing = db.scalar(select(VoiceToolAction).where(VoiceToolAction.config_id == config.id, VoiceToolAction.action_id == event_key))
        if existing is not None:
            return {"received": True, "duplicate": True, "routed": existing.result.get("routed") is True}
        raise HTTPException(status_code=503, detail="Webhook receipt is temporarily unavailable") from None
    if event_type == "call.hangup":
        call.ended_at = call.ended_at or datetime.now(timezone.utc)
        if call.status not in {"appointment_booked", "appointment_cancelled", "transferred"}:
            call.status = "ended"
        db.commit()
        return {"received": True}
    if event_type == "call.gather.ended":
        if call.ended_at is not None or call.status not in {"routed", "in_progress"}:
            return {"received": True, "authenticated": False}
        auth_controller = VoiceCallerAuth(db, settings)
        if not auth_controller.valid_challenge(call, str(call_payload.get("client_state") or "")):
            return {"received": True, "authenticated": False}
        call.pin_challenge_hash = None
        call.pin_challenge_expires_at = None
        digits = call_payload.get("digits")
        result = auth_controller.verify_gather(call, digits if isinstance(digits, str) else "")
        if media_mode:
            call.source_context = {**(call.source_context or {}), "pin_gather_status": "authenticated" if result["authenticated"] else "refused"}
        receipt.result = {**receipt.result, "authenticated": result["authenticated"]}
        AuditLogService(db).record(actor_user_id=call.authenticated_user_id if result["authenticated"] else None,
            action="voice_pin_authentication_succeeded" if result["authenticated"] else "voice_pin_authentication_failed",
            target_type="voice_call", target_id=str(call.id), company_id=call.company_id,
            metadata={"authenticated": result["authenticated"]}, commit=False)
        db.commit()
        return {"received": True, "authenticated": result["authenticated"]}
    if event_type == "call.bridged":
        if call.ended_at is None and call.status in {"routed", "routing", "in_progress"}:
            call.status = "in_progress"
            db.commit()
        return {"received": True}
    if event_type == "call.answered" and (call.ended_at is not None or call.status != "answering"):
        return {"received": True, "routed": False}
    if not media_mode and not settings.retell_api_key:
        call.status = "awaiting_configuration"
        db.commit()
        return {"received": True, "routed": False, "status": "READY_FOR_OWNER_ACTION"}
    try:
        target = service.provider.inbound_target(config) if not media_mode else None
    except ValueError:
        call.status = "awaiting_configuration"
        db.commit()
        return {"received": True, "routed": False, "status": "READY_FOR_OWNER_ACTION"}
    claim = db.scalar(
        select(VoiceCall)
        .where(VoiceCall.id == call.id)
        .with_for_update()
    )
    if claim is None:
        raise HTTPException(status_code=500, detail="Inbound call record could not be claimed")
    expected_status = "incoming" if event_type == "call.initiated" else "answering"
    if claim.status != expected_status or claim.ended_at is not None:
        return {"received": True, "routed": claim.status in {"routing", "routed", "in_progress"}, "duplicate": True}
    claim.status = "answering" if event_type == "call.initiated" else "in_progress" if media_mode else "routing"
    db.commit()
    try:
        if event_type == "call.initiated":
            command_id = str(UUID(hashlib.sha256(f"answer:{call.id}".encode("utf-8")).hexdigest()[:32]))
            await service.telnyx.answer_call(call.telnyx_call_control_id, command_id=command_id)
            return {"received": True, "routed": False, "status": "answering"}
        if media_mode:
            client_state = issue_media_client_state(db, settings, call.id, public_mode=True)
            stream_url = settings.telnyx_media_stream_base_url.rstrip("/") + "/" + str(call.id)
            command_id = str(UUID(hashlib.sha256(f"media:{call.id}".encode()).hexdigest()[:32]))
            await service.telnyx.start_media_stream(call.telnyx_call_control_id, stream_url=stream_url,
                client_state=client_state, command_id=command_id)
            receipt.result = {**receipt.result, "routed": True, "transport": "telnyx_media"}
            db.commit()
            return {"received": True, "routed": True}
        command_id = str(UUID(hashlib.sha256(f"transfer:{call.id}".encode("utf-8")).hexdigest()[:32]))
        await service.telnyx.transfer_call(call.telnyx_call_control_id, target, config.telnyx_phone_number, command_id=command_id, call_reference=str(call.id))
    except Exception as exc:
        db.refresh(call)
        if call.ended_at is None:
            call.status = "routing_outcome_unknown"
        db.commit()
        logger.warning("Telnyx inbound routing failed for voice call %s", call.id)
        raise HTTPException(status_code=502, detail="Unable to route inbound call") from exc
    db.refresh(call)
    if call.ended_at is None:
        call.status = "routed"
    receipt.result = {**receipt.result, "routed": True}
    db.commit()
    return {"received": True, "routed": True}


@router.post("/retell/webhook", dependencies=[Depends(rate_limit("voice_retell_webhook", "rate_limit_webhook_per_minute"))])
async def retell_webhook(
    request: Request,
    x_avenqo_voice_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    envelope = await request.json()
    call_data = envelope.get("call") if isinstance(envelope.get("call"), dict) else {}
    agent_id = str(call_data.get("agent_id") or "")
    config = db.scalar(select(VoiceBusinessConfig).where(
        VoiceBusinessConfig.retell_agent_id == agent_id,
        VoiceBusinessConfig.enabled.is_(True),
    ))
    if config is None or not hmac.compare_digest(config.voice_api_key_hash, _api_key_hash(x_avenqo_voice_key or "")):
        raise HTTPException(status_code=401, detail="Invalid tenant voice API key")
    _ensure_voice_access(db, config.company_id)
    service = _orchestrator(db, settings)
    event = str(envelope.get("event") or "")
    call_id = str(call_data.get("call_id") or "")
    if not call_id:
        raise HTTPException(status_code=422, detail="Retell call_id is required")
    caller_phone = str(call_data.get("from_number") or call_data.get("from") or "") or None
    sip_headers = call_data.get("custom_sip_headers") if isinstance(call_data.get("custom_sip_headers"), dict) else {}
    reference = next((value for key, value in sip_headers.items() if key.casefold() == "x-avenqo-call-id"), None)
    if reference is None:
        call = db.scalar(select(VoiceCall).where(VoiceCall.config_id == config.id, VoiceCall.retell_call_id == call_id))
    else:
        try:
            reference_id = UUID(str(reference))
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid call correlation") from None
        call = db.scalar(select(VoiceCall).where(VoiceCall.id == reference_id, VoiceCall.company_id == config.company_id, VoiceCall.config_id == config.id))
        if call is not None and call.retell_call_id not in {None, call_id}:
            raise HTTPException(status_code=409, detail="Call correlation conflict")
        if call is not None:
            call.retell_call_id = call_id
    if call is None:
        raise HTTPException(status_code=404, detail="Correlated tenant call not found")
    if event in {"call_started", "call_connected"}:
        call.status = "in_progress"
        db.commit()
    elif event in {"call_ended", "call_analyzed"}:
        await service.finish_call(config, call_id, call_data)
    return {"received": True}


async def _run_tool(
    tool_name: str,
    request: VoiceToolRequest,
    api_key: str | None,
    db: Session,
    settings: Settings,
) -> dict[str, Any]:
    config, service = _authenticated_voice_config(db, settings, api_key)
    try:
        return await service.execute_tool(config, request.call_id, request.action_id, tool_name, request.arguments)
    except (ValueError, LookupError, PermissionError) as exc:
        return {"success": False, "error": str(exc)}


def _tool_route(tool_name: str):
    async def endpoint(
        request: VoiceToolRequest,
        x_avenqo_voice_key: str | None = Header(default=None),
        db: Session = Depends(get_db),
        settings: Settings = Depends(get_settings),
    ) -> dict[str, Any]:
        return await _run_tool(tool_name, request, x_avenqo_voice_key, db, settings)
    return endpoint


router.add_api_route("/tools/check_availability", _tool_route("check_availability"), methods=["POST"],
                     dependencies=[Depends(rate_limit("voice_tool", "rate_limit_ai_per_minute"))])
router.add_api_route("/tools/book_appointment", _tool_route("book_appointment"), methods=["POST"],
                     dependencies=[Depends(rate_limit("voice_tool", "rate_limit_ai_per_minute"))])
router.add_api_route("/tools/reschedule_appointment", _tool_route("reschedule_appointment"), methods=["POST"],
                     dependencies=[Depends(rate_limit("voice_tool", "rate_limit_ai_per_minute"))])
router.add_api_route("/tools/cancel_appointment", _tool_route("cancel_appointment"), methods=["POST"],
                     dependencies=[Depends(rate_limit("voice_tool", "rate_limit_ai_per_minute"))])
router.add_api_route("/tools/transfer_to_human", _tool_route("transfer_to_human"), methods=["POST"],
                     dependencies=[Depends(rate_limit("voice_tool", "rate_limit_ai_per_minute"))])
router.add_api_route("/tools/get_business_info", _tool_route("get_business_info"), methods=["POST"],
                     dependencies=[Depends(rate_limit("voice_tool", "rate_limit_ai_per_minute"))])
router.add_api_route("/tools/take_message", _tool_route("take_message"), methods=["POST"],
                     dependencies=[Depends(rate_limit("voice_tool", "rate_limit_ai_per_minute"))])
router.add_api_route("/tools/request_caller_verification", _tool_route("request_caller_verification"), methods=["POST"],
                     dependencies=[Depends(rate_limit("voice_tool", "rate_limit_ai_per_minute"))])
router.add_api_route("/tools/request_pin_authentication", _tool_route("request_pin_authentication"), methods=["POST"],
                     dependencies=[Depends(rate_limit("voice_pin_request", "rate_limit_ai_per_minute"))])
router.add_api_route("/tools/verify_caller", _tool_route("verify_caller"), methods=["POST"],
                     dependencies=[Depends(rate_limit("voice_tool", "rate_limit_ai_per_minute"))])


async def _voice_central_execute(
    request: VoiceToolRequest,
    x_avenqo_voice_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    central_ai: CentralAIService = Depends(get_central_ai_service),
    prediction_service=Depends(get_prediction_service),
    *,
    metrics_only: bool = True,
) -> dict[str, Any]:
    config, orchestrator = _authenticated_voice_config(db, settings, x_avenqo_voice_key)
    call = orchestrator._resolve_call(config, request.call_id)
    if call.ended_at is not None or call.status in {"ended", "failed", "rejected"}:
        return {"success": False, "status": "call_ended", "error": "voice_call_not_active"}
    if call.caller_type not in {"OWNER", "EMPLOYEE"} or call.authenticated_user_id is None:
        return {"success": False, "status": "not_authorized", "error": "caller_verification_required"}
    membership = db.scalar(select(CompanyMembership).where(
        CompanyMembership.company_id == config.company_id,
        CompanyMembership.user_id == call.authenticated_user_id,
        CompanyMembership.is_active.is_(True),
    ))
    user = db.scalar(select(User).where(
        User.id == call.authenticated_user_id,
        User.company_id == config.company_id,
        User.is_active.is_(True),
    ))
    company = db.get(Company, config.company_id)
    if membership is None or user is None or company is None:
        return {"success": False, "status": "not_authorized", "error": "caller_membership_unavailable"}
    permissions = frozenset(permissions_for(membership.role))
    if "ai:use" not in permissions:
        return {"success": False, "status": "not_authorized", "error": "ai_permission_required"}
    auth_session = VoiceCallerAuth(db, settings).valid_session(call)
    if auth_session is None:
        return {"success": False, "status": "not_authorized", "error": "caller_verification_required"}
    permissions = permissions.intersection(auth_session.permissions)

    question = redact_voice_secrets(request.arguments.get("question") or request.arguments.get("transcript") or "").strip()
    if not question or len(question) > 12_000:
        raise HTTPException(status_code=422, detail="A valid business metrics question is required")
    detection = detect_spoken_language(question, preferred_locale=call.locale or config.preferred_language)
    if detection.locale is not None:
        call.locale = detection.locale

    action_key = voice_action_key(config.id, call.id, "get_business_metrics" if metrics_only else "central_ai", request.action_id,
        f"{auth_session.principal_id}:{auth_session.authenticated_at.isoformat()}")
    legacy = db.scalar(select(VoiceToolAction).where(
        VoiceToolAction.config_id == config.id, VoiceToolAction.action_id == request.action_id,
    ))
    if legacy is not None:
        return {"success": False, "status": "not_authorized", "error": "legacy_action_context_unavailable"}

    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy import text
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"voice_metrics:{config.company_id}:{action_key}"},
        )
    existing = db.scalar(select(VoiceToolAction).where(
        VoiceToolAction.config_id == config.id,
        VoiceToolAction.action_id == action_key,
    ))
    if existing is not None:
        return existing.result
    action = VoiceToolAction(
        company_id=config.company_id,
        config_id=config.id,
        action_id=action_key,
        tool_name="get_business_metrics" if metrics_only else "central_ai",
        result={"status": "in_progress"},
    )
    db.add(action)
    try:
        db.commit()
    except Exception:
        db.rollback()
        existing = db.scalar(select(VoiceToolAction).where(
            VoiceToolAction.config_id == config.id,
            VoiceToolAction.action_id == action_key,
        ))
        if existing is not None:
            return existing.result
        raise

    tenant = TenantContext(company_id=config.company_id, user_id=user.id)
    call.source_context = resolve_voice_source_context(db, tenant)
    db.commit()
    if call.central_conversation_id is None:
        conversation = ConversationService(db).create(
            config.company_id,
            user.id,
            f"Voice call {call.id}",
            call.locale or config.preferred_language,
        )
        call.central_conversation_id = conversation.id
        db.commit()
    request_id = hashlib.sha256(
        f"avenqo-voice:{config.company_id}:{call.id}:{request.action_id}".encode("utf-8")
    ).hexdigest()
    try:
        result = await central_ai.execute(
            tenant,
            user.id,
            call.central_conversation_id,
            question,
            permissions=permissions,
            capabilities=resolve_tenant_capabilities(db, tenant, prediction_service),
            request_id=request_id,
            user_language=call.locale or config.preferred_language,
            company_country=company.country or "",
            company_currency=company.currency_code,
            company_timezone=company.timezone or config.timezone_name,
            page_context="/voice",
            locale_explicit=False,
            spoken_language_input=True,
        )
        metrics_tools = {
            "get_business_overview",
            "get_sales_summary",
            "get_sales_trend",
            "get_sales_comparison",
            "get_top_products",
            "get_inventory_summary",
        }
        grounded_metrics = any(
            outcome.get("tool") in metrics_tools and outcome.get("success") is True
            for outcome in result.tool_outcomes
        )
        safe_result = {
            "success": result.status == "success" and bool(result.answer) and (
                grounded_metrics if metrics_only else any(
                    outcome.get("success") is True and outcome.get("confirmed") is True
                    for outcome in result.tool_outcomes
                )
            ),
            "status": result.status,
            "answer": result.answer,
            "selected_agent": result.selected_agent,
            "remaining_ai_credits": result.remaining_ai_credits,
            "tool_outcomes": list(result.tool_outcomes),
        }
    except Exception:
        logger.exception("Central AI voice metrics execution failed", extra={"company_id": str(config.company_id), "call_id": str(call.id)})
        safe_result = {"success": False, "status": "error", "error": "voice_metrics_unavailable"}
    action = db.scalar(select(VoiceToolAction).where(
        VoiceToolAction.config_id == config.id,
        VoiceToolAction.action_id == action_key,
    ))
    if action is not None:
        action.result = safe_result
        db.commit()
    return safe_result


@router.post("/tools/business_metrics", dependencies=[Depends(rate_limit("voice_business_metrics", "rate_limit_ai_per_minute"))])
async def voice_business_metrics(
    request: VoiceToolRequest,
    x_avenqo_voice_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    central_ai: CentralAIService = Depends(get_central_ai_service),
    prediction_service=Depends(get_prediction_service),
) -> dict[str, Any]:
    return await _voice_central_execute(request, x_avenqo_voice_key, db, settings, central_ai, prediction_service)


@router.post("/tools/central_ai", dependencies=[Depends(rate_limit("voice_central_ai", "rate_limit_ai_per_minute"))])
async def voice_central_agent(
    request: VoiceToolRequest,
    x_avenqo_voice_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    central_ai: CentralAIService = Depends(get_central_ai_service),
    prediction_service=Depends(get_prediction_service),
) -> dict[str, Any]:
    return await _voice_central_execute(
        request, x_avenqo_voice_key, db, settings, central_ai, prediction_service, metrics_only=False,
    )
