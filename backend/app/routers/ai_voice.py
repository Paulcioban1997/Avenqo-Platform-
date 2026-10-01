"""Voice Central sessions: browser/mobile STT text enters the same AI Central path."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.central.service import CentralAIService
from backend.app.ai.request_identity import resolve_ai_request_id
from backend.app.core.locale_catalog import LOCALES, resolve_locale
from backend.app.core.permissions import permissions_for
from backend.app.dependencies.ai_authorization import get_active_ai_membership
from backend.app.dependencies.auth import CurrentIdentity, get_current_identity, get_tenant_context
from backend.app.core.security import decode_access_token
from backend.app.dependencies.central_ai import get_central_ai_service
from backend.app.database import get_db
from backend.app.models import AuthSession, User, VoiceCentralSession
from backend.app.schemas.voice_central import (
    VoiceSessionCreate,
    VoiceSessionResponse,
    VoiceTurnRequest,
    VoiceTurnResponse,
)
from shared.ai_engine.contracts import TenantContext

router = APIRouter(
    prefix="/ai/voice",
    tags=["ai-voice"],
    dependencies=[Depends(get_active_ai_membership)],
)


def _response(session: VoiceCentralSession) -> VoiceSessionResponse:
    return VoiceSessionResponse(
        id=session.id,
        conversation_id=session.conversation_id,
        locale=session.locale,
        status=session.status,
        stt_provider=session.stt_provider,
        tts_provider=session.tts_provider,
        realtime_provider=session.realtime_provider,
        text_fallback=True,
        voice_capability="browser_stt_text_fallback",
    )


@router.post("/sessions", response_model=VoiceSessionResponse)
def create_session(
    request: VoiceSessionCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db),
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
    locale = resolve_locale(request.locale or identity.user.company.preferred_language)
    session = VoiceCentralSession(
        company_id=tenant.company_id,
        user_id=identity.user.id,
        conversation_id=request.conversation_id,
        request_id=request_id,
        locale=locale,
        status="active",
        stt_provider="browser_speech",
        tts_provider=None,
        realtime_provider=None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _response(session)


@router.post("/sessions/{session_id}/turn", response_model=VoiceTurnResponse)
async def turn(
    session_id: UUID,
    request: VoiceTurnRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    identity: CurrentIdentity = Depends(get_current_identity),
    membership=Depends(get_active_ai_membership),
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
    request_id = resolve_ai_request_id(
        request.request_id,
        tenant_id=tenant.company_id,
        user_id=identity.user.id,
        conversation_id=session.conversation_id,
    )
    result = await service.execute(
        tenant,
        identity.user.id,
        session.conversation_id,
        request.transcript,
        permissions=frozenset(permissions_for(membership.role)),
        capabilities=frozenset(),
        request_id=request_id,
        user_language=session.locale,
        company_country=identity.user.company.country or "",
        company_currency=getattr(identity.user.company, "currency_code", None) or "USD",
        company_timezone=identity.user.company.timezone or "UTC",
        locale_explicit=True,
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
async def stream_session(websocket: WebSocket, session_id: UUID, db: Session = Depends(get_db)) -> None:
    """Secure text/audio event transport; audio adapters are provider-configured."""

    authorization = websocket.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = decode_access_token(token)
        user_id = UUID(str(claims["sub"]))
        tenant_id = UUID(str(claims["tenant_id"]))
    except (ValueError, KeyError, TypeError):
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
    if user is None or not user.is_active or user.company_id != tenant_id:
        await websocket.close(code=4403)
        return
    await websocket.accept()
    await websocket.send_json({"type": "lifecycle", "status": "listening", "session_id": str(session.id)})
    try:
        while True:
            event = await websocket.receive_json()
            event_type = str(event.get("type") or "")
            if event_type == "interrupt":
                session.interruption_count += 1
                db.commit()
                await websocket.send_json({"type": "lifecycle", "status": "interrupted"})
                continue
            if event_type == "audio":
                await websocket.send_json({
                    "type": "error",
                    "code": "external_configuration_required",
                    "status": "text_fallback",
                })
                continue
            if event_type == "close":
                break
            if event_type != "transcript":
                await websocket.send_json({"type": "error", "code": "voice_event_invalid"})
                continue
            transcript = str(event.get("transcript") or "").strip()
            if not transcript:
                continue
            await websocket.send_json({"type": "lifecycle", "status": "thinking"})
            await websocket.send_json({
                "type": "transcript",
                "transcript": transcript,
                "status": "text_fallback",
                "requires_http_turn": True,
            })
            # The authenticated HTTP turn endpoint executes the same AI Central
            # graph and credit/idempotency path until a live STT provider is configured.
    except WebSocketDisconnect:
        session.status = "closed"
        session.ended_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        if session.status == "active":
            session.status = "closed"
            session.ended_at = datetime.now(timezone.utc)
            db.commit()
