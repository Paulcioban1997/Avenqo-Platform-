"""Tenant-secured inbound voice agent, Telnyx webhooks, and Retell tools."""

from __future__ import annotations

import base64
import binascii
import hmac
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import Settings, get_settings
from backend.app.core.rate_limit import rate_limit
from backend.app.database import get_db
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, require_permission
from backend.app.dependencies.subscription import require_active_subscription
from backend.app.models import BillingAccount, VoiceBusinessConfig, VoiceCall
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.schemas.voice import VoiceConfigCreatedResponse, VoiceConfigRequest, VoiceConfigResponse, VoiceToolRequest
from backend.app.voice.providers import RetellVoiceProvider, TelnyxClient
from backend.app.voice.service import VoiceOrchestrator, _api_key_hash
from shared.ai_engine.contracts import TenantContext

router = APIRouter(prefix="/voice", tags=["voice-agent"])
manage_voice = require_permission("modules:manage")
logger = logging.getLogger("avenqo.voice")


def _orchestrator(db: Session, settings: Settings) -> VoiceOrchestrator:
    return VoiceOrchestrator(db, settings, RetellVoiceProvider(settings), TelnyxClient(settings))


def _config_response(config: VoiceBusinessConfig) -> VoiceConfigResponse:
    return VoiceConfigResponse.model_validate(VoiceOrchestrator.public_config(config))


def _verify_telnyx_signature(request: Request, raw_body: bytes, settings: Settings) -> None:
    signature = request.headers.get("telnyx-signature-ed25519")
    timestamp = request.headers.get("telnyx-timestamp")
    if not signature or not timestamp or not settings.telnyx_public_key:
        raise HTTPException(status_code=401, detail="Telnyx webhook signature is not configured")
    try:
        timestamp_float = float(timestamp)
        if abs(time.time() - timestamp_float) > settings.telnyx_webhook_max_age_seconds:
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
    data, call_payload = _call_event_data(envelope)
    event_type = str(data.get("event_type") or "")
    call_control_id = str(call_payload.get("call_control_id") or "")
    if event_type != "call.initiated":
        if event_type == "call.hangup" and call_control_id:
            call = db.scalar(select(VoiceCall).where(VoiceCall.telnyx_call_control_id == call_control_id))
            if call and call.status not in {"ended", "appointment_booked", "appointment_cancelled", "transferred"}:
                call.status = "ended"
                call.ended_at = datetime.now(timezone.utc)
                db.commit()
        return {"received": True}
    destination = str(call_payload.get("to") or "")
    config = db.scalar(select(VoiceBusinessConfig).where(
        VoiceBusinessConfig.telnyx_phone_number == destination,
        VoiceBusinessConfig.enabled.is_(True),
    ))
    if config is None:
        return {"received": True, "routed": False}
    service = _orchestrator(db, settings)
    try:
        _ensure_voice_access(db, config.company_id)
    except HTTPException:
        return {"received": True, "routed": False}
    call = service.record_inbound(config, call_payload)
    claim = db.scalar(
        select(VoiceCall)
        .where(VoiceCall.id == call.id)
        .with_for_update()
    )
    if claim is None:
        raise HTTPException(status_code=500, detail="Inbound call record could not be claimed")
    if claim.status != "incoming":
        return {"received": True, "routed": claim.status in {"routing", "routed", "in_progress"}, "duplicate": True}
    claim.status = "routing"
    db.commit()
    target = service.provider.inbound_target(config)
    try:
        await service.telnyx.transfer_call(call.telnyx_call_control_id, target, config.telnyx_phone_number)
    except Exception as exc:
        call.status = "failed"
        db.commit()
        logger.exception("Telnyx inbound routing failed for voice call %s", call.id)
        raise HTTPException(status_code=502, detail="Unable to route inbound call") from exc
    call.status = "routed"
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
    call = service._resolve_call(config, call_id, caller_phone=caller_phone)
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
