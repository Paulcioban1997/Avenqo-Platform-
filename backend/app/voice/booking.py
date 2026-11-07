"""Shared VoiceCall booking markers used by Retell _book and Central inbound tools."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import VoiceCall


def mark_voice_call_booked(
    db: Session,
    *,
    company_id: UUID,
    appointment_id: UUID,
    call: VoiceCall | None = None,
    conversation_id: UUID | None = None,
) -> VoiceCall | None:
    """Set appointment_booked on the tenant call without changing company_id."""
    if call is None and conversation_id is not None:
        call = db.scalar(
            select(VoiceCall).where(
                VoiceCall.company_id == company_id,
                VoiceCall.central_conversation_id == conversation_id,
            )
        )
    if call is None or call.company_id != company_id:
        return None
    call.appointment_id = appointment_id
    call.status = "appointment_booked"
    context = dict(call.source_context or {})
    context["appointment_confirmed"] = True
    call.source_context = context
    db.commit()
    return call
