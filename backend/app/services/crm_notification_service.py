"""Truthful, idempotent appointment notification recording."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.dependencies.auth import get_account_notifier
from backend.app.models.crm import CRMAppointment, CRMClient, CRMCommunication


class CRMNotificationService:
    """Records notification intent without claiming external delivery."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def record_appointment_event(
        self,
        company_id: UUID,
        appointment: CRMAppointment,
        client: CRMClient,
        event: str,
    ) -> None:
        settings = get_settings()
        email_status = "queued" if settings.email_delivery_configured else "blocked_external_configuration"
        await self._record(
            company_id,
            appointment,
            client,
            channel="email",
            event=event,
            recipient=client.email,
            status=email_status,
        )
        sms_status = "queued" if settings.telnyx_api_key else "blocked_external_configuration"
        await self._record(
            company_id,
            appointment,
            client,
            channel="sms",
            event=event,
            recipient=client.phone,
            status=sms_status,
        )

    async def _record(
        self,
        company_id: UUID,
        appointment: CRMAppointment,
        client: CRMClient,
        *,
        channel: str,
        event: str,
        recipient: str | None,
        status: str,
    ) -> None:
        if not recipient:
            status = "blocked_external_configuration"
        elif channel == "email" and status == "queued":
            try:
                get_account_notifier().send_transactional(
                    recipient,
                    f"Avenqo — rendez-vous {event}",
                    f"Votre rendez-vous {event} est associé au dossier Avenqo {appointment.id}.",
                )
                status = "sent"
            except Exception:
                status = "failed"
        elif channel == "sms":
            # No CRM tenant sender identity is configured here; never invent one.
            status = "blocked_external_configuration"
        subject = f"appointment:{appointment.id}:{event}:{channel}"
        existing = self._session.scalar(
            select(CRMCommunication).where(
                CRMCommunication.company_id == company_id,
                CRMCommunication.appointment_id == appointment.id,
                CRMCommunication.channel == channel,
                CRMCommunication.subject == subject,
            )
        )
        if existing is not None:
            return
        content = f"Notification {event} pour le rendez-vous {appointment.id}."
        self._session.add(
            CRMCommunication(
                company_id=company_id,
                client_id=client.id,
                appointment_id=appointment.id,
                channel=channel,
                direction="outbound",
                subject=subject,
                content=content,
                status=status,
            )
        )
