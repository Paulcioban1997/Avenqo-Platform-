"""Voice Central sessions share AI Central authorization and conversation state."""

import asyncio
import base64
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.central.service import CentralAIService
from backend.app.ai.chat.exceptions import AIServiceUnavailableError
from backend.app.ai.request_identity import resolve_ai_request_id
from backend.app.config.settings import get_settings
from backend.app.core.locale_catalog import (
    BY_BCP47,
    BY_LOCALE,
    detect_spoken_language,
    resolve_locale,
)
from backend.app.core.permissions import permissions_for
from backend.app.dependencies.ai_authorization import get_active_ai_membership
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.core.security import decode_access_token
from backend.app.dependencies.central_ai import get_central_ai_service
from backend.app.database import get_db
from backend.app.models import AuthSession, BillingAccount, CompanyMembership, User, VoiceCentralSession
from backend.app.services.retail_source_service import RetailSourceService
from backend.app.services.module_entitlement_service import ModuleEntitlementService
from backend.app.dependencies.subscription import require_active_subscription
from backend.app.voice.adapters import ExternalVoiceConfigurationRequired, OpenAIAudioConfig, OpenAIRealtimeAudioAdapter
from backend.app.voice.usage import VoiceUsageLedger, voice_pricing_catalog
from backend.app.voice.service import resolve_voice_source_context
from backend.app.schemas.voice_central import (
    VoiceSessionCreate,
    VoiceSessionResponse,
    VoiceStreamTicketResponse,
    VoiceTurnRequest,
    VoiceTurnResponse,
)
from shared.ai_engine.contracts import TenantContext

router = APIRouter(
    prefix="/ai/voice",
    tags=["ai-voice"],
)


def _enforce_voice_access(db: Session, tenant: TenantContext, membership: CompanyMembership) -> None:
    if "ai:use" not in permissions_for(membership.role):
        raise HTTPException(status_code=403, detail="AI permission is required")
    account = db.scalar(select(BillingAccount).where(BillingAccount.company_id == tenant.company_id))
    if account is not None:
        db.refresh(account)
    require_active_subscription(tenant, db)
    if not ModuleEntitlementService(db).can_use_module(tenant, "voice"):
        raise HTTPException(status_code=403, detail="Voice module is not active for this tenant")


def get_voice_membership(
    tenant: TenantContext = Depends(get_tenant_context),
    membership: CompanyMembership = Depends(get_active_ai_membership),
    db: Session = Depends(get_db),
) -> CompanyMembership:
    _enforce_voice_access(db, tenant, membership)
    return membership


def _response(session: VoiceCentralSession) -> VoiceSessionResponse:
    realtime = _realtime_available(session.locale)
    return VoiceSessionResponse(
        id=session.id,
        conversation_id=session.conversation_id,
        locale=session.locale,
        detected_language=session.detected_language,
        detected_locale=session.detected_locale,
        language_confidence=session.language_confidence,
        status=session.status,
        stt_provider="openai" if realtime else "browser_speech",
        tts_provider="openai" if realtime else None,
        realtime_provider="openai" if realtime else None,
        text_fallback=not realtime,
        voice_capability="realtime_audio" if realtime else "browser_stt_text_fallback",
    )


def _realtime_available(locale: str) -> bool:
    settings = get_settings()
    requested = locale.casefold().replace("_", "-")
    supported = {
        value.casefold().replace("_", "-")
        for value in settings.voice_realtime_supported_locales
    }
    try:
        canonical = resolve_locale(locale).casefold().replace("_", "-")
    except ValueError:
        canonical = requested
    return bool(
        (requested in BY_LOCALE or requested in BY_BCP47)
        and (requested in supported or canonical in supported)
        and settings.voice_realtime_provider == "openai"
        and settings.voice_realtime_model
        and settings.voice_stt_provider == "openai"
        and settings.voice_stt_model
        and settings.voice_tts_provider == "openai"
        and settings.voice_tts_model
        and settings.voice_tts_voice
        and settings.openai_api_key
    )


def _realtime_adapter() -> OpenAIRealtimeAudioAdapter:
    settings = get_settings()
    return OpenAIRealtimeAudioAdapter(
        OpenAIAudioConfig(settings.openai_api_key, settings.voice_stt_model, settings.voice_tts_model, settings.voice_tts_voice),
        settings.voice_realtime_model,
    )


def _resolve_voice_turn_language(
    session: VoiceCentralSession,
    transcript: str,
    db: Session,
):
    detection = detect_spoken_language(transcript, preferred_locale=session.locale)
    session.detected_language = detection.language_code
    session.detected_locale = detection.locale
    session.language_confidence = detection.confidence
    if detection.locale is not None and detection.locale != session.locale:
        session.previous_locale = session.locale
        session.locale = detection.locale
    db.commit()
    return detection


def _audit_session_source(session: VoiceCentralSession, db: Session) -> None:
    session.source_context = resolve_voice_source_context(
        db, TenantContext(company_id=session.company_id, user_id=session.user_id)
    )
    db.commit()


@router.post("/sessions", response_model=VoiceSessionResponse)
def create_session(
    request: VoiceSessionCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
    membership: CompanyMembership = Depends(get_voice_membership),
) -> VoiceSessionResponse:
    request_id = resolve_ai_request_id(
        request.request_id,
        tenant_id=tenant.company_id,
        user_id=identity.user.id,
        conversation_id=request.conversation_id,
    )
    existing = db.scalar(
        select(VoiceCentralSession).where(
            VoiceCentralSession.company_id == tenant.company_id,
            VoiceCentralSession.request_id == request_id,
        )
    )
    if existing is not None:
        return _response(existing)
    requested_locale = request.locale if "locale" in request.model_fields_set else identity.user.company.preferred_language or "fr"
    normalized = requested_locale.casefold().replace("_", "-")
    locale = resolve_locale(requested_locale) if normalized in BY_LOCALE or normalized in BY_BCP47 else requested_locale
    realtime = _realtime_available(locale)
    session = VoiceCentralSession(
        company_id=tenant.company_id,
        user_id=identity.user.id,
        conversation_id=request.conversation_id,
        request_id=request_id,
        locale=locale,
        status="active",
        stt_provider="openai" if realtime else "browser_speech",
        tts_provider="openai" if realtime else None,
        realtime_provider="openai" if realtime else None,
        source_context=resolve_voice_source_context(
            db, TenantContext(company_id=tenant.company_id, user_id=identity.user.id)
        ),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _response(session)


@router.post(
    "/sessions/{session_id}/stream-ticket",
    response_model=VoiceStreamTicketResponse,
)
def stream_ticket(
    session_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
    membership: CompanyMembership = Depends(get_voice_membership),
) -> VoiceStreamTicketResponse:
    session = db.scalar(select(VoiceCentralSession).where(
        VoiceCentralSession.id == session_id,
        VoiceCentralSession.company_id == tenant.company_id,
        VoiceCentralSession.user_id == identity.user.id,
        VoiceCentralSession.status == "active",
    ))
    if session is None:
        raise HTTPException(status_code=404, detail="Voice session not found")
    settings = get_settings()
    now = int(datetime.now(timezone.utc).timestamp())
    ticket = jwt.encode({
        "type": "voice_stream", "sub": str(identity.user.id), "tenant_id": str(tenant.company_id),
        "session_id": str(session_id), "auth_session_id": str(identity.auth_session.id),
        "iat": now, "exp": now + 30, "iss": settings.auth_jwt_issuer, "aud": settings.auth_jwt_audience,
    }, settings.auth_jwt_secret, algorithm=settings.auth_jwt_algorithm)
    return VoiceStreamTicketResponse(
        ticket=ticket,
        realtime=_realtime_available(session.locale),
    )


async def _execute_voice(service, *args, **kwargs):
    try:
        return await service.execute(*args, **kwargs)
    except AIServiceUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/turn", response_model=VoiceTurnResponse)
async def turn(
    session_id: UUID,
    request: VoiceTurnRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    membership=Depends(get_voice_membership),
    service: CentralAIService = Depends(get_central_ai_service),
    db: Session = Depends(get_db),
) -> VoiceTurnResponse:
    session = db.scalar(
        select(VoiceCentralSession).where(
            VoiceCentralSession.id == session_id,
            VoiceCentralSession.company_id == tenant.company_id,
            VoiceCentralSession.user_id == identity.user.id,
        )
    )
    if session is None or session.status != "active":
        raise HTTPException(status_code=404, detail="Voice session not found")
    detection = _resolve_voice_turn_language(session, request.transcript, db)
    _audit_session_source(session, db)
    request_id = resolve_ai_request_id(
        request.request_id,
        tenant_id=tenant.company_id,
        user_id=identity.user.id,
        conversation_id=session.conversation_id,
    )
    result = await _execute_voice(service,
        tenant,
        identity.user.id,
        session.conversation_id,
        request.transcript,
        permissions=frozenset(permissions_for(membership.role)),
        capabilities=frozenset(),
        request_id=request_id,
        user_language=detection.locale or session.locale,
        company_country=identity.user.company.country or "",
        company_currency=getattr(identity.user.company, "currency_code", None) or "USD",
        company_timezone=identity.user.company.timezone or "UTC",
        locale_explicit=detection.locale is not None,
        spoken_language_input=True,
    )
    return VoiceTurnResponse(
        session_id=session.id,
        conversation_id=session.conversation_id,
        transcript=request.transcript,
        answer=result.answer,
        status=result.status,
        tts_status="external_configuration_required",
        tts_provider=None,
        remaining_ai_credits=result.remaining_ai_credits,
    )


@router.post("/sessions/{session_id}/end", response_model=VoiceSessionResponse)
def end_session(
    session_id: UUID,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
    membership: CompanyMembership = Depends(get_active_ai_membership),
) -> VoiceSessionResponse:
    session = db.scalar(
        select(VoiceCentralSession).where(
            VoiceCentralSession.id == session_id,
            VoiceCentralSession.company_id == tenant.company_id,
            VoiceCentralSession.user_id == identity.user.id,
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Voice session not found")
    session.status = "ended"
    session.ended_at = datetime.now(timezone.utc)
    db.commit()
    return _response(session)


@router.websocket("/sessions/{session_id}/stream")
async def stream_session(
    websocket: WebSocket,
    session_id: UUID,
    db: Session = Depends(get_db),
    service: CentralAIService = Depends(get_central_ai_service),
) -> None:
    token = websocket.headers.get("authorization", "").removeprefix("Bearer ").strip()
    protocols = [part.strip() for part in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    browser_ticket = next((part[7:] for part in protocols if part.startswith("ticket.")), "")
    try:
        if token:
            claims = decode_access_token(token)
            auth_session_id = UUID(str(claims["session_id"]))
        else:
            settings = get_settings()
            claims = jwt.decode(
                browser_ticket, settings.auth_jwt_secret,
                algorithms=[settings.auth_jwt_algorithm], issuer=settings.auth_jwt_issuer,
                audience=settings.auth_jwt_audience,
            )
            if claims.get("type") != "voice_stream" or claims.get("session_id") != str(session_id):
                raise ValueError("Invalid voice stream ticket")
            auth_session_id = UUID(str(claims["auth_session_id"]))
        user_id = UUID(str(claims["sub"]))
        tenant_id = UUID(str(claims["tenant_id"]))
    except (ValueError, KeyError, TypeError, jwt.InvalidTokenError):
        await websocket.close(code=4401)
        return

    session = db.scalar(
        select(VoiceCentralSession).where(
            VoiceCentralSession.id == session_id,
            VoiceCentralSession.company_id == tenant_id,
            VoiceCentralSession.user_id == user_id,
            VoiceCentralSession.status == "active",
        )
    )
    if session is None:
        await websocket.close(code=4404)
        return
    user = db.get(User, user_id)
    def authorized() -> CompanyMembership | None:
        if user is not None:
            db.refresh(user)
        auth_session = db.get(AuthSession, auth_session_id)
        if auth_session is not None:
            db.refresh(auth_session)
        membership = db.scalar(select(CompanyMembership).where(
            CompanyMembership.user_id == user_id,
            CompanyMembership.company_id == tenant_id,
            CompanyMembership.is_active.is_(True),
        ))
        if membership is not None:
            db.refresh(membership)
        db.refresh(session)
        if (
            user is None or not user.is_active or user.company_id != tenant_id
            or auth_session is None or auth_session.revoked_at is not None
            or auth_session.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc)
            or session.status != "active"
        ):
            return None
        if membership is None or not membership.is_active:
            return None
        try:
            _enforce_voice_access(db, TenantContext(tenant_id, user_id), membership)
        except HTTPException:
            return None
        return membership

    if authorized() is None:
        await websocket.close(code=4403)
        return

    _audit_session_source(session, db)
    db.commit()
    await websocket.accept(subprotocol="avenqo.voice" if browser_ticket else None)
    adapter = None
    settings = get_settings()
    if _realtime_available(session.locale):
        adapter = _realtime_adapter()
        try:
            await adapter.open(locale=session.locale)
        except Exception:
            usage_service = getattr(service, "usage_service", None)
            if usage_service is not None:
                ledger = VoiceUsageLedger(
                    usage_service,
                    voice_pricing_catalog(settings.ai_model_rate_card),
                    company_id=tenant_id,
                    user_id=user_id,
                    conversation_id=session.conversation_id,
                    plan_code=ModuleEntitlementService(db).get_company_plan(TenantContext(tenant_id)).code.value,
                )
                failed_item = f"realtime-connect-{uuid4().hex}"
                ledger.record_provider_failure(
                    failed_item,
                    model=settings.voice_realtime_model,
                    operation="voice_realtime_connect",
                    event_id=f"connect-error-{uuid4().hex}",
                    failure_category="connection_failed",
                )
                ledger.settle(failed_item)
            await adapter.close()
            adapter = None
    usage_ledger = None
    if adapter is not None and (usage_service := getattr(service, "usage_service", None)) is not None:
        usage_ledger = VoiceUsageLedger(
            usage_service,
            voice_pricing_catalog(settings.ai_model_rate_card),
            company_id=tenant_id,
            user_id=user_id,
            conversation_id=session.conversation_id,
            plan_code=ModuleEntitlementService(db).get_company_plan(TenantContext(tenant_id)).code.value,
        )
    await websocket.send_json({
        "type": "lifecycle", "status": "listening", "session_id": str(session.id),
        "conversation_id": str(session.conversation_id), "text_fallback": adapter is None,
        "next_audio_sequence": int(getattr(session, "last_audio_sequence", -1)) + 1,
    })
    epoch = 0
    seen_items: set[str] = set()
    seen_frames: set[int] = set()
    speaking = False
    response_id: str | None = None
    pending_audio_item: str | None = None
    current_input_item_id: str | None = None
    response_items: dict[str, str] = {}
    ignored_items: set[str] = set()
    send_lock = asyncio.Lock()
    central_lock = asyncio.Lock()

    async def send(event: dict) -> None:
        async with send_lock:
            await websocket.send_json(event)

    async def execute_final(item_id: str, transcript: str, turn_epoch: int) -> None:
        nonlocal speaking, pending_audio_item
        async with central_lock:
            if turn_epoch != epoch or not transcript.strip():
                return
            if usage_ledger is not None and not usage_ledger.reserve(item_id):
                return
            membership = authorized()
            if membership is None:
                await websocket.close(code=4403)
                return
            detection = _resolve_voice_turn_language(session, transcript, db)
            await send({"type": "transcript", "transcript": transcript, "status": "final"})
            await send({"type": "lifecycle", "status": "thinking"})
            request_id = resolve_ai_request_id(
                item_id, tenant_id=tenant_id, user_id=user_id, conversation_id=session.conversation_id,
            )
            central_attempts = []
            try:
                result = await service.execute(
                    TenantContext(company_id=tenant_id), user_id, session.conversation_id, transcript,
                    permissions=frozenset(permissions_for(membership.role)), capabilities=frozenset(),
                    request_id=request_id, user_language=detection.locale or session.locale,
                    company_country=user.company.country or "",
                    company_currency=getattr(user.company, "currency_code", None) or "USD",
                    company_timezone=user.company.timezone or "UTC",
                    locale_explicit=detection.locale is not None,
                    spoken_language_input=True,
                    allow_existing_reservation=usage_ledger is not None,
                    attempt_sink=central_attempts,
                )
            finally:
                if usage_ledger is not None:
                    usage_ledger.add_attempts(item_id, central_attempts)
            if turn_epoch != epoch:
                if usage_ledger is not None:
                    usage_ledger.settle(item_id)
                return
            if usage_ledger is not None:
                usage_ledger.attribute(item_id, result.selected_agent, result.selected_agent)
            await send({
                "type": "answer", "answer": result.answer, "status": result.status,
                "conversation_id": str(session.conversation_id),
                "remaining_ai_credits": result.remaining_ai_credits,
            })
            if result.answer and adapter is not None:
                speaking = True
                pending_audio_item = item_id
                await adapter.speak(result.answer)
            else:
                if usage_ledger is not None:
                    usage_ledger.settle(item_id)
                await send({"type": "lifecycle", "status": "listening"})

    async def provider_events() -> None:
        nonlocal epoch, speaking, response_id, pending_audio_item, current_input_item_id, adapter
        assert adapter is not None
        try:
            async for event in adapter.events():
                event_type = getattr(event, "type", "")
                if event_type == "input_audio_buffer.speech_started":
                    epoch += 1
                    item_id = str(getattr(event, "item_id", ""))
                    current_input_item_id = item_id or current_input_item_id
                    if item_id and usage_ledger is not None and not usage_ledger.reserve(item_id):
                        ignored_items.add(item_id)
                    if speaking:
                        speaking = False
                        await adapter.interrupt()
                    await send({"type": "lifecycle", "status": "interrupted"})
                    await send({"type": "lifecycle", "status": "listening"})
                elif event_type == "conversation.item.input_audio_transcription.completed":
                    item_id = str(getattr(event, "item_id", ""))
                    if item_id and item_id not in seen_items and item_id not in ignored_items:
                        seen_items.add(item_id)
                        if usage_ledger is not None:
                            if not usage_ledger.reserve(item_id):
                                ignored_items.add(item_id)
                                continue
                            usage_ledger.record_transcription(
                                item_id,
                                event,
                                model=settings.voice_stt_model,
                            )
                        await execute_final(item_id, str(getattr(event, "transcript", "")), epoch)
                elif event_type == "response.created" and speaking:
                    response_id = str(getattr(getattr(event, "response", None), "id", ""))
                    if response_id and pending_audio_item:
                        response_items[response_id] = pending_audio_item
                        pending_audio_item = None
                elif event_type == "response.output_audio.delta" and speaking and response_id == getattr(event, "response_id", None):
                    await send({"type": "audio", "audio": event.delta, "format": "pcm16", "rate": 24000})
                elif event_type == "response.done":
                    response = getattr(event, "response", None)
                    completed_response_id = str(getattr(response, "id", ""))
                    item_id = response_items.pop(completed_response_id, None)
                    if item_id and usage_ledger is not None:
                        usage_ledger.record_realtime_response(
                            item_id,
                            event,
                            model=settings.voice_realtime_model,
                        )
                        usage_ledger.settle(item_id)
                    if completed_response_id == response_id:
                        speaking = False
                        response_id = None
                        await send({"type": "lifecycle", "status": "listening"})
        except Exception:
            speaking = False
            if usage_ledger is not None:
                failed_item = (
                    response_items.get(response_id or "")
                    or pending_audio_item
                    or current_input_item_id
                    or f"realtime-stream-{uuid4().hex}"
                )
                usage_ledger.record_provider_failure(
                    failed_item,
                    model=settings.voice_realtime_model,
                    operation="voice_realtime_stream",
                    event_id=f"stream-error-{uuid4().hex}",
                    failure_category="stream_error",
                )
                usage_ledger.settle(failed_item)
                usage_ledger.settle_pending()
            await adapter.close()
            adapter = None
            await send({"type": "error", "code": "realtime_provider_unavailable", "status": "text_fallback"})

    provider_task = asyncio.create_task(provider_events()) if adapter is not None else None
    try:
        while True:
            db.commit()
            event = await websocket.receive_json()
            if authorized() is None:
                await websocket.close(code=4403)
                break
            event_type = str(event.get("type") or "")
            if event_type == "interrupt":
                epoch += 1
                speaking = False
                session.interruption_count += 1
                db.commit()
                if adapter is not None:
                    await adapter.interrupt()
                await send({"type": "lifecycle", "status": "interrupted"})
                continue
            if event_type == "audio":
                if adapter is None:
                    await send({"type": "error", "code": "external_configuration_required", "status": "text_fallback"})
                    continue
                sequence = event.get("sequence")
                if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
                    await send({"type": "error", "code": "voice_audio_invalid"})
                    continue
                db.refresh(session)
                last_audio_sequence = int(getattr(session, "last_audio_sequence", -1))
                if sequence <= last_audio_sequence or sequence in seen_frames:
                    continue
                try:
                    audio = base64.b64decode(event.get("audio", ""), validate=True)
                    if not audio or len(audio) > 48000:
                        raise ValueError("Invalid audio frame")
                except (ValueError, TypeError):
                    await send({"type": "error", "code": "voice_audio_invalid"})
                    continue
                seen_frames.add(sequence)
                session.last_audio_sequence = sequence
                db.commit()
                await adapter.send_audio(audio)
                continue
            if event_type == "close":
                session.status = "closed"
                session.ended_at = datetime.now(timezone.utc)
                db.commit()
                break
            await send({"type": "error", "code": "voice_event_invalid"})
    except WebSocketDisconnect:
        pass
    finally:
        if provider_task is not None:
            provider_task.cancel()
            await asyncio.gather(provider_task, return_exceptions=True)
        if usage_ledger is not None:
            usage_ledger.settle_pending()
        if adapter is not None:
            await adapter.close()
