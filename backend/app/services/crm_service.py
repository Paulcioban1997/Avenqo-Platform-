"""Core business service for Avenqo CRM AI operations and tenant data management."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from dataclasses import dataclass
import logging
import re
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, desc, func, or_, select, text
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.models.crm import (
    CRMActivity,
    CRMActivityLog,
    CRMAppointment,
    CRMAutomation,
    CRMCalendarConnection,
    CRMClient,
    CRMCommunication,
    CRMEmployee,
    CRMNote,
    CRMOpportunity,
    CRMPipeline,
    CRMPipelineStage,
    CRMService as CRMServiceModel,
)
from backend.app.models.company import Company
from backend.app.services.calendar.base import CalendarEventData, CalendarProviderError
from backend.app.services.calendar.google_provider import GoogleCalendarProvider
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher
from backend.app.services.crm_availability_service import AvailabilityUnavailable, CRMAvailabilityService
from backend.app.services.crm_notification_service import CRMNotificationService
from backend.app.services.crm_recipient_policy import evaluate_crm_recipient, is_test_email

logger = logging.getLogger(__name__)


def _tenant_month_bounds(now: datetime, timezone_name: str | None) -> tuple[datetime, datetime]:
    try:
        tenant_timezone = ZoneInfo(timezone_name or "UTC")
    except ZoneInfoNotFoundError:
        tenant_timezone = timezone.utc
    local_now = now.astimezone(tenant_timezone)
    start_local = datetime(local_now.year, local_now.month, 1, tzinfo=tenant_timezone)
    if local_now.month == 12:
        next_local = datetime(local_now.year + 1, 1, 1, tzinfo=tenant_timezone)
    else:
        next_local = datetime(local_now.year, local_now.month + 1, 1, tzinfo=tenant_timezone)
    return start_local.astimezone(timezone.utc), next_local.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class AppointmentMutationResult:
    appointment: CRMAppointment | None
    calendar_sync: str
    error: str | None = None


class CRMService:
    """Enterprise multi-tenant CRM management service."""

    def __init__(self, session: Session, cipher: ConnectorSecretCipher | None = None) -> None:
        self._session = session
        self._cipher = cipher
        self._availability = CRMAvailabilityService(session, cipher)

    # --- KPI Metrics ---

    def get_kpis(self, company_id: UUID) -> dict[str, Any]:
        """Calculates real tenant KPI metrics directly from database records."""
        now = datetime.now(timezone.utc)
        tenant_timezone = self._session.scalar(
            select(Company.timezone).where(Company.id == company_id)
        )
        start_of_month, start_of_next_month = _tenant_month_bounds(now, tenant_timezone)
        # 1. Active clients count
        active_clients = self._session.scalar(
            select(func.count(CRMClient.id)).where(
                CRMClient.company_id == company_id,
                CRMClient.is_deleted.is_(False),
                CRMClient.status == "active",
            )
        ) or 0

        # 2. Appointments this month
        apts_this_month = self._session.scalar(
            select(func.count(CRMAppointment.id)).where(
                CRMAppointment.company_id == company_id,
                CRMAppointment.is_deleted.is_(False),
                CRMAppointment.status != "cancelled",
                CRMAppointment.start_time >= start_of_month,
                CRMAppointment.start_time < start_of_next_month,
            )
        ) or 0

        # 3. Attendance rate
        completed_count = self._session.scalar(
            select(func.count(CRMAppointment.id)).where(
                CRMAppointment.company_id == company_id,
                CRMAppointment.is_deleted.is_(False),
                CRMAppointment.status == "completed",
            )
        ) or 0

        no_show_count = self._session.scalar(
            select(func.count(CRMAppointment.id)).where(
                CRMAppointment.company_id == company_id,
                CRMAppointment.is_deleted.is_(False),
                CRMAppointment.status == "no_show",
            )
        ) or 0

        total_tracked = completed_count + no_show_count
        attendance_rate = round((completed_count / total_tracked * 100), 1) if total_tracked > 0 else 100.0

        # 4. Total revenue generated (completed appointments + won opportunities)
        apt_revenue = self._session.scalar(
            select(func.sum(CRMAppointment.price)).where(
                CRMAppointment.company_id == company_id,
                CRMAppointment.is_deleted.is_(False),
                CRMAppointment.status.in_(["completed", "confirmed"]),
            )
        ) or 0.0

        won_opp_revenue = self._session.scalar(
            select(func.sum(CRMOpportunity.amount)).where(
                CRMOpportunity.company_id == company_id,
                CRMOpportunity.stage == "closed_won",
            )
        ) or 0.0

        total_revenue = float(apt_revenue) + float(won_opp_revenue)

        return {
            "active_clients": active_clients,
            "appointments_this_month": apts_this_month,
            "attendance_rate_percent": attendance_rate,
            "total_revenue_generated": round(total_revenue, 2),
            "currency": "CAD",
        }

    # --- Client Management ---

    def list_clients(
        self,
        company_id: UUID,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CRMClient]:
        query = select(CRMClient).where(
            CRMClient.company_id == company_id,
            CRMClient.is_deleted.is_(False),
        )
        if status:
            query = query.where(CRMClient.status == status)
        if search:
            pat = f"%{search.strip()}%"
            query = query.where(
                or_(
                    CRMClient.first_name.ilike(pat),
                    CRMClient.last_name.ilike(pat),
                    (CRMClient.first_name + " " + CRMClient.last_name).ilike(pat),
                    CRMClient.email.ilike(pat),
                    CRMClient.phone.ilike(pat),
                    CRMClient.company_name.ilike(pat),
                )
            )
        query = query.order_by(CRMClient.created_at.desc()).offset(offset).limit(limit)
        return list(self._session.scalars(query).all())

    def get_client(self, company_id: UUID, client_id: UUID) -> CRMClient | None:
        return self._session.scalars(
            select(CRMClient).where(
                CRMClient.id == client_id,
                CRMClient.company_id == company_id,
                CRMClient.is_deleted.is_(False),
            )
        ).first()

    def resolve_client_for_appointment(
        self,
        company_id: UUID,
        identifier: str,
        *,
        email: str | None = None,
        phone: str | None = None,
    ) -> tuple[CRMClient | None, str | None]:
        """Resolve only an exact ID/email/phone or one unique CRM name match."""
        explicit_email = (email or "").strip().lower()
        identifier_email = identifier.strip().lower() if "@" in identifier else ""
        normalized_email = explicit_email or identifier_email
        if normalized_email:
            if not self.is_valid_customer_email(normalized_email):
                return None, "L'adresse courriel du client est invalide."
            client = self._session.scalars(
                select(CRMClient).where(
                    CRMClient.company_id == company_id,
                    func.lower(CRMClient.email) == normalized_email,
                    CRMClient.is_deleted.is_(False),
                )
            ).first()
            if client:
                return client, None
            return None, "Aucun client ne correspond à cette adresse courriel. Demandez le bon dossier client."

        explicit_phone = (phone or "").strip()
        identifier_phone = identifier.strip() if self._normalize_phone(identifier) else ""
        normalized_phone = self._normalize_phone(explicit_phone or identifier_phone)
        if explicit_phone or identifier_phone:
            candidates = [
                client
                for client in self.list_clients(company_id, limit=500)
                if self._normalize_phone(client.phone) == normalized_phone
            ]
            if len(candidates) == 1:
                return candidates[0], None
            return None, "Aucun client unique ne correspond à ce numéro de téléphone."

        candidates = self.list_clients(company_id, search=identifier, limit=20)
        if len(candidates) == 1:
            return candidates[0], None
        if len(candidates) > 1:
            return None, "Plusieurs clients correspondent. Demandez l'adresse courriel ou le téléphone."
        return None, "Client introuvable. Demandez l'adresse courriel réelle avant de créer le rendez-vous."

    def create_client(self, company_id: UUID, data: dict[str, Any], actor_name: str = "Utilisateur") -> CRMClient:
        email = str(data.get("email") or "").strip().lower() or None
        phone = self._normalize_phone(data.get("phone"))
        existing = self._find_existing_client(company_id, email=email, phone=phone)
        if existing:
            return existing

        client = CRMClient(
            company_id=company_id,
            first_name=data["first_name"].strip(),
            last_name=data["last_name"].strip(),
            email=email or "",
            phone=phone,
            preferred_language=data.get("preferred_language", "fr"),
            company_name=data.get("company_name"),
            industry_type=data.get("industry_type", "general"),
            industry_metadata=data.get("industry_metadata", {}),
            status=data.get("status", "active"),
            tags=data.get("tags", []),
        )
        self._session.add(client)
        self._session.flush()

        self._log_activity(
            company_id,
            entity_type="client",
            entity_id=client.id,
            action="create",
            actor_name=actor_name,
            details={"name": client.full_name, "email": client.email},
        )
        self._session.commit()
        return client

    @staticmethod
    def _normalize_phone(phone: Any) -> str | None:
        digits = "".join(character for character in str(phone or "") if character.isdigit())
        return digits or None

    @staticmethod
    def is_valid_customer_email(email: str | None) -> bool:
        return not is_test_email(email)

    def _find_existing_client(
        self,
        company_id: UUID,
        *,
        email: str | None = None,
        phone: str | None = None,
    ) -> CRMClient | None:
        query = select(CRMClient).where(
            CRMClient.company_id == company_id,
            CRMClient.is_deleted.is_(False),
        )
        candidates = list(self._session.scalars(query).all())
        for client in candidates:
            if email and client.email and client.email.strip().lower() == email:
                return client
            if phone and self._normalize_phone(client.phone) == phone:
                return client
        return None

    def update_client(self, company_id: UUID, client_id: UUID, data: dict[str, Any], actor_name: str = "Utilisateur") -> CRMClient | None:
        client = self.get_client(company_id, client_id)
        if not client:
            return None

        for field in ["first_name", "last_name", "email", "phone", "preferred_language", "company_name", "industry_type", "status"]:
            if field in data and data[field] is not None:
                setattr(client, field, data[field])
        if "industry_metadata" in data:
            client.industry_metadata = data["industry_metadata"]
        if "tags" in data:
            client.tags = data["tags"]

        self._log_activity(
            company_id,
            entity_type="client",
            entity_id=client.id,
            action="update",
            actor_name=actor_name,
            details=data,
        )
        self._session.commit()
        return client

    def get_client_360(self, company_id: UUID, client_id: UUID) -> dict[str, Any] | None:
        """Assembles complete Client 360 profile: details, appointments, notes, communications and revenue."""
        client = self.get_client(company_id, client_id)
        if not client:
            return None

        # Appointments
        apts = list(
            self._session.scalars(
                select(CRMAppointment)
                .where(
                    CRMAppointment.company_id == company_id,
                    CRMAppointment.client_id == client_id,
                    CRMAppointment.is_deleted.is_(False),
                )
                .order_by(CRMAppointment.start_time.desc())
            ).all()
        )

        # Notes
        notes = list(
            self._session.scalars(
                select(CRMNote)
                .where(
                    CRMNote.company_id == company_id,
                    CRMNote.client_id == client_id,
                )
                .order_by(CRMNote.created_at.desc())
            ).all()
        )

        # Communications
        comms = list(
            self._session.scalars(
                select(CRMCommunication)
                .where(
                    CRMCommunication.company_id == company_id,
                    CRMCommunication.client_id == client_id,
                )
                .order_by(CRMCommunication.sent_at.desc())
            ).all()
        )

        total_spent = sum(a.price for a in apts if a.status in {"completed", "confirmed"})

        return {
            "client": {
                "id": str(client.id),
                "full_name": client.full_name,
                "first_name": client.first_name,
                "last_name": client.last_name,
                "email": client.email,
                "phone": client.phone,
                "preferred_language": client.preferred_language,
                "company_name": client.company_name,
                "industry_type": client.industry_type,
                "industry_metadata": client.industry_metadata,
                "status": client.status,
                "tags": client.tags,
                "attendance_rate": client.attendance_rate,
                "created_at": client.created_at.isoformat(),
            },
            "metrics": {
                "total_appointments": len(apts),
                "completed_appointments": sum(1 for a in apts if a.status == "completed"),
                "total_spent": round(total_spent, 2),
            },
            "appointments": [
                {
                    "id": str(a.id),
                    "title": a.title,
                    "start_time": a.start_time.isoformat(),
                    "end_time": a.end_time.isoformat(),
                    "status": a.status,
                    "price": a.price,
                    "notes": a.notes,
                }
                for a in apts
            ],
            "notes": [
                {
                    "id": str(n.id),
                    "author_name": n.author_name,
                    "content": n.content,
                    "pinned": n.pinned,
                    "created_at": n.created_at.isoformat(),
                }
                for n in notes
            ],
            "communications": [
                {
                    "id": str(c.id),
                    "channel": c.channel,
                    "direction": c.direction,
                    "subject": c.subject,
                    "content": c.content,
                    "status": c.status,
                    "sent_at": c.sent_at.isoformat(),
                }
                for c in comms
            ],
        }

    # --- Appointment Management ---

    def list_appointments(
        self,
        company_id: UUID,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        status: str | None = None,
        employee_id: UUID | None = None,
        client_id: UUID | None = None,
        search: str | None = None,
        limit: int | None = None,
        starting_before: datetime | None = None,
    ) -> list[dict[str, Any]]:
        query = select(CRMAppointment).where(
            CRMAppointment.company_id == company_id,
            CRMAppointment.is_deleted.is_(False),
        )
        if start_date:
            query = query.where(CRMAppointment.start_time >= start_date)
        if starting_before:
            query = query.where(CRMAppointment.start_time < starting_before)
        if end_date:
            query = query.where(CRMAppointment.end_time <= end_date)
        if status:
            query = query.where(CRMAppointment.status == status)
        if employee_id:
            query = query.where(CRMAppointment.employee_id == employee_id)
        if client_id:
            query = query.where(CRMAppointment.client_id == client_id)

        query = query.order_by(CRMAppointment.start_time.asc())
        if limit is not None:
            query = query.limit(min(max(limit, 1), 500))
        apts = list(self._session.scalars(query).all())

        results = []
        for a in apts:
            client = self._session.get(CRMClient, a.client_id)
            service = self._session.get(CRMServiceModel, a.service_id) if a.service_id else None
            employee = self._session.get(CRMEmployee, a.employee_id) if a.employee_id else None

            if search:
                needle = search.strip().lower()
                searchable = " ".join(
                    value.lower()
                    for value in (
                        a.title,
                        a.notes or "",
                        client.full_name if client else "",
                        service.name if service else "",
                    )
                )
                if needle not in searchable:
                    continue

            results.append({
                "id": str(a.id),
                "client_id": str(a.client_id),
                "client_name": client.full_name if client else "Client Inconnu",
                "client_phone": client.phone if client else None,
                "client_email": client.email if client else None,
                "service_id": str(a.service_id) if a.service_id else None,
                "service_name": service.name if service else None,
                "employee_id": str(a.employee_id) if a.employee_id else None,
                "employee_name": employee.name if employee else "Non assigné",
                "employee_color": employee.color_hex if employee else "#00D4FF",
                "title": a.title,
                "start_time": a.start_time.isoformat(),
                "end_time": a.end_time.isoformat(),
                "duration_minutes": a.duration_minutes,
                "status": a.status,
                "price": a.price,
                "currency": a.currency,
                "notes": a.notes,
                "industry_data": a.industry_data,
                "calendar_provider": a.calendar_provider,
                "external_event_id": a.external_event_id,
            })
        return results

    async def create_appointment(
        self,
        company_id: UUID,
        data: dict[str, Any],
        actor_name: str = "Utilisateur",
        check_conflicts: bool = True,
    ) -> tuple[CRMAppointment | None, str | None]:
        """Creates appointment with conflict detection and external Google Calendar synchronization."""
        start_time = self._availability.normalize(company_id, data["start_time"])
        duration = data.get("duration_minutes", 60)
        end_time = self._availability.normalize(company_id, data["end_time"]) if data.get("end_time") else (start_time + timedelta(minutes=duration))
        employee_id = data.get("employee_id")

        idempotency_key = str(data.get("idempotency_key") or "").strip() or None
        if idempotency_key:
            existing = self._session.scalar(
                select(CRMAppointment).where(
                    CRMAppointment.company_id == company_id,
                    CRMAppointment.idempotency_key == idempotency_key,
                    CRMAppointment.is_deleted.is_(False),
                )
            )
            if existing:
                return existing, None

        await self._acquire_appointment_lock(company_id)

        if idempotency_key:
            existing = self._session.scalar(select(CRMAppointment).where(
                CRMAppointment.company_id == company_id,
                CRMAppointment.idempotency_key == idempotency_key,
                CRMAppointment.is_deleted.is_(False),
            ))
            if existing:
                return existing, None

        if check_conflicts:
            try:
                has_conflict, reason = await self._availability.check_booking_conflict(
                    company_id, start_time, end_time, employee_id, data.get("service_id")
                )
            except AvailabilityUnavailable as exc:
                return None, str(exc)
            if has_conflict:
                return None, reason or "Conflit d'horaire détecté."

        # Verify client exists
        client = self.get_client(company_id, data["client_id"])
        if not client:
            return None, "Le client spécifié n'existe pas."

        # Resolve price from service if not provided
        price = data.get("price", 0.0)
        title = data.get("title")
        if data.get("service_id"):
            svc = self._session.get(CRMServiceModel, data["service_id"])
            if svc and svc.company_id == company_id:
                if price == 0.0:
                    price = svc.price
                if not title:
                    title = f"{svc.name} - {client.full_name}"

        if not title:
            title = f"Rendez-vous - {client.full_name}"

        raw_industry_data = data.get("industry_data")
        appointment = CRMAppointment(
            company_id=company_id,
            client_id=data["client_id"],
            service_id=data.get("service_id"),
            employee_id=employee_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration,
            status=data.get("status", "confirmed"),
            price=price,
            currency=data.get("currency", "CAD"),
            notes=data.get("notes"),
            industry_data=(raw_industry_data if isinstance(raw_industry_data, dict) else {}),
            idempotency_key=idempotency_key,
        )
        self._session.add(appointment)
        self._session.flush()

        # External Calendar Sync (Google Calendar)
        calendar_sync, sync_error = await self._sync_to_external_calendar(
            company_id, appointment, client, action="create"
        )
        if calendar_sync == "failed":
            self._session.rollback()
            return None, sync_error or "Google Calendar did not confirm the appointment."
        await CRMNotificationService(self._session).record_appointment_event(
            company_id, appointment, client, "created"
        )

        # Increment client appointment count
        client.appointments_count += 1

        self._log_activity(
            company_id,
            entity_type="appointment",
            entity_id=appointment.id,
            action="create",
            actor_name=actor_name,
            details={"title": appointment.title, "start": appointment.start_time.isoformat()},
        )
        self._session.commit()
        return appointment, None

    def _lock_appointment_writes(self, company_id: UUID) -> None:
        """Serialize tenant appointment changes across Postgres app workers."""
        if self._session.get_bind().dialect.name == "postgresql":
            self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"crm_appointments:{company_id}"},
            )

    async def _acquire_appointment_lock(self, company_id: UUID) -> None:
        if self._session.get_bind().dialect.name == "postgresql":
            import asyncio
            await asyncio.to_thread(self._lock_appointment_writes, company_id)
        else:
            self._lock_appointment_writes(company_id)

    async def update_appointment(
        self,
        company_id: UUID,
        appointment_id: UUID,
        data: dict[str, Any],
        actor_name: str = "Utilisateur",
        check_conflicts: bool = True,
    ) -> tuple[CRMAppointment | None, str | None]:
        await self._acquire_appointment_lock(company_id)
        apt = self._session.scalars(
            select(CRMAppointment).where(
                CRMAppointment.id == appointment_id,
                CRMAppointment.company_id == company_id,
                CRMAppointment.is_deleted.is_(False),
            )
        ).first()
        if not apt:
            return None, "Rendez-vous introuvable."

        supplied_start = data.get("start_time", apt.start_time)
        if "start_time" not in data and supplied_start.tzinfo is None:
            supplied_start = supplied_start.replace(tzinfo=timezone.utc)
        start_time = self._availability.normalize(company_id, supplied_start)
        duration = data.get("duration_minutes", apt.duration_minutes)
        end_time = self._availability.normalize(company_id, data["end_time"]) if data.get("end_time") else (start_time + timedelta(minutes=duration))
        emp_id = data.get("employee_id", apt.employee_id)

        if check_conflicts and ("start_time" in data or "employee_id" in data or "duration_minutes" in data):
            try:
                has_conflict, reason = await self._availability.check_booking_conflict(
                    company_id, start_time, end_time, emp_id, data.get("service_id", apt.service_id), exclude_appointment_id=appointment_id
                )
            except AvailabilityUnavailable as exc:
                return None, str(exc)
            if has_conflict:
                return None, reason or "Conflit d'horaire détecté pour ce déplacement."

        apt.start_time = start_time
        apt.end_time = end_time
        apt.duration_minutes = duration
        if "employee_id" in data:
            apt.employee_id = emp_id
        if "status" in data:
            apt.status = data["status"]
        if "notes" in data:
            apt.notes = data["notes"]
        if "price" in data:
            apt.price = data["price"]
        if "title" in data:
            apt.title = data["title"]
        if "industry_data" in data:
            apt.industry_data = data["industry_data"]

        client = self.get_client(company_id, apt.client_id)
        if client:
            calendar_sync, sync_error = await self._sync_to_external_calendar(
                company_id, apt, client, action="update"
            )
            if calendar_sync == "failed":
                self._session.rollback()
                return None, sync_error or "Google Calendar did not confirm the update."
            await CRMNotificationService(self._session).record_appointment_event(
                company_id, apt, client, "updated"
            )

        self._log_activity(
            company_id,
            entity_type="appointment",
            entity_id=apt.id,
            action="update",
            actor_name=actor_name,
            details=data,
        )
        self._session.commit()
        return apt, None

    async def cancel_appointment(
        self,
        company_id: UUID,
        appointment_id: UUID,
        actor_name: str = "Utilisateur",
    ) -> bool:
        result = await self.cancel_appointment_detailed(company_id, appointment_id, actor_name)
        return result.appointment is not None and result.calendar_sync != "failed"

    async def cancel_appointment_detailed(
        self,
        company_id: UUID,
        appointment_id: UUID,
        actor_name: str = "Utilisateur",
    ) -> AppointmentMutationResult:
        await self._acquire_appointment_lock(company_id)
        apt = self._session.scalars(
            select(CRMAppointment).where(
                CRMAppointment.id == appointment_id,
                CRMAppointment.company_id == company_id,
                CRMAppointment.is_deleted.is_(False),
            )
        ).first()
        if not apt:
            return AppointmentMutationResult(None, "not_found", "Rendez-vous introuvable.")

        if apt.status == "cancelled" and not apt.external_event_id:
            return AppointmentMutationResult(apt, "already_cancelled")

        apt.status = "cancelled"

        client = self.get_client(company_id, apt.client_id)
        calendar_sync = "not_configured"
        sync_error = None
        if client:
            calendar_sync, sync_error = await self._sync_to_external_calendar(
                company_id, apt, client, action="delete"
            )
            if calendar_sync == "failed":
                self._session.rollback()
                return AppointmentMutationResult(None, calendar_sync, sync_error)
            await CRMNotificationService(self._session).record_appointment_event(
                company_id, apt, client, "cancelled"
            )

        self._log_activity(
            company_id,
            entity_type="appointment",
            entity_id=apt.id,
            action="cancel",
            actor_name=actor_name,
            details={"status": "cancelled", "calendar_sync": calendar_sync},
        )
        self._session.commit()
        return AppointmentMutationResult(apt, calendar_sync, sync_error)

    async def delete_appointment(
        self,
        company_id: UUID,
        appointment_id: UUID,
        actor_name: str = "Utilisateur",
    ) -> AppointmentMutationResult:
        await self._acquire_appointment_lock(company_id)
        apt = self._session.scalars(
            select(CRMAppointment).where(
                CRMAppointment.id == appointment_id,
                CRMAppointment.company_id == company_id,
                CRMAppointment.is_deleted.is_(False),
            )
        ).first()
        if not apt:
            return AppointmentMutationResult(None, "not_found", "Rendez-vous introuvable.")

        client = self.get_client(company_id, apt.client_id)
        if client:
            calendar_sync, sync_error = await self._sync_to_external_calendar(
                company_id, apt, client, action="delete"
            )
            if sync_error:
                return AppointmentMutationResult(apt, calendar_sync, sync_error)

        apt.is_deleted = True
        apt.status = "cancelled"
        self._log_activity(
            company_id,
            entity_type="appointment",
            entity_id=apt.id,
            action="delete",
            actor_name=actor_name,
            details={"permanent": True, "calendar_sync": "deleted"},
        )
        self._session.commit()
        return AppointmentMutationResult(apt, "deleted")

    # --- External Calendar Sync Helper ---

    @staticmethod
    def _google_event_datetime(event: dict[str, Any], field: str) -> datetime | None:
        value = (event.get(field) or {}).get("dateTime")
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed

    async def sync_from_google(
        self,
        company_id: UUID,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict[str, int]:
        """Reconcile Google events into tenant CRM records without inventing clients."""
        conn = self._session.scalar(
            select(CRMCalendarConnection).where(
                CRMCalendarConnection.company_id == company_id,
                CRMCalendarConnection.provider == "google",
                CRMCalendarConnection.sync_status.in_(("connected", "syncing", "error")),
            )
        )
        if conn is None or self._cipher is None:
            raise CalendarProviderError("Google Calendar non connecté.")

        now = datetime.now(timezone.utc)
        start_time = start_time or now - timedelta(days=30)
        end_time = end_time or now + timedelta(days=365)
        settings = get_settings()
        provider = GoogleCalendarProvider(
            settings.google_calendar_client_id,
            settings.google_calendar_client_secret,
            settings.google_calendar_redirect_uri,
        )
        credentials = self._cipher.decrypt(conn.encrypted_credentials)
        conn.sync_status = "syncing"
        self._session.commit()
        try:
            try:
                events = await provider.list_events(credentials, start_time, end_time, conn.calendar_id)
            except CalendarProviderError as exc:
                refresh_token = credentials.get("refresh_token")
                if "401" not in str(exc) or not refresh_token:
                    raise
                refreshed = await provider.refresh_access_token(str(refresh_token))
                credentials = {**credentials, **refreshed, "refresh_token": refresh_token}
                conn.encrypted_credentials = self._cipher.encrypt(credentials)
                events = await provider.list_events(credentials, start_time, end_time, conn.calendar_id)

            stats = {"fetched": len(events), "created": 0, "updated": 0, "cancelled": 0, "skipped": 0}
            await self._acquire_appointment_lock(company_id)
            for event in events:
                event_id = str(event.get("id") or "").strip()
                if not event_id:
                    stats["skipped"] += 1
                    continue
                existing = self._session.scalar(
                    select(CRMAppointment).where(
                        CRMAppointment.company_id == company_id,
                        CRMAppointment.calendar_provider == "google",
                        CRMAppointment.external_event_id == event_id,
                    )
                )
                cancelled = event.get("status") == "cancelled"
                if existing is not None:
                    if existing.is_deleted:
                        stats["skipped"] += 1
                        continue
                    if cancelled:
                        if existing.status != "cancelled":
                            existing.status = "cancelled"
                            stats["cancelled"] += 1
                        continue
                    start = self._google_event_datetime(event, "start")
                    end = self._google_event_datetime(event, "end")
                    if start is None or end is None or end <= start:
                        stats["skipped"] += 1
                        continue
                    existing.title = str(event.get("summary") or existing.title)
                    existing.start_time = start
                    existing.end_time = end
                    existing.duration_minutes = max(int((end - start).total_seconds() // 60), 1)
                    existing.notes = event.get("description") or existing.notes
                    existing.status = "confirmed"
                    stats["updated"] += 1
                    continue
                if cancelled:
                    stats["skipped"] += 1
                    continue
                start = self._google_event_datetime(event, "start")
                end = self._google_event_datetime(event, "end")
                if start is None or end is None or end <= start:
                    stats["skipped"] += 1
                    continue
                attendee_emails = {
                    str(attendee.get("email") or "").strip().lower()
                    for attendee in event.get("attendees") or []
                    if attendee.get("email")
                }
                attendee_emails.discard(conn.account_email.strip().lower())
                clients = list(
                    self._session.scalars(
                        select(CRMClient).where(
                            CRMClient.company_id == company_id,
                            CRMClient.is_deleted.is_(False),
                            CRMClient.is_synthetic.is_(False),
                            CRMClient.communications_enabled.is_(True),
                            func.lower(CRMClient.email).in_(attendee_emails),
                        )
                    ).all()
                ) if attendee_emails else []
                unique_clients = {client.id: client for client in clients}
                if len(unique_clients) != 1:
                    stats["skipped"] += 1
                    continue
                client = next(iter(unique_clients.values()))
                self._session.add(CRMAppointment(
                    company_id=company_id,
                    client_id=client.id,
                    title=str(event.get("summary") or "Rendez-vous Google Calendar"),
                    start_time=start,
                    end_time=end,
                    duration_minutes=max(int((end - start).total_seconds() // 60), 1),
                    status="confirmed",
                    notes=event.get("description"),
                    industry_data={},
                    idempotency_key=f"google:{event_id}",
                    calendar_provider="google",
                    external_event_id=event_id,
                ))
                client.appointments_count += 1
                stats["created"] += 1
            conn.sync_status = "connected"
            conn.sync_error = None
            conn.last_synced_at = now
            self._session.commit()
            return stats
        except Exception as exc:
            self._session.rollback()
            conn = self._session.get(CRMCalendarConnection, conn.id)
            if conn is not None:
                conn.sync_status = "error"
                conn.sync_error = "Synchronisation Google Calendar impossible."
                self._session.commit()
            raise CalendarProviderError("Synchronisation Google Calendar impossible.") from exc

    async def list_google_events(
        self,
        company_id: UUID,
        *,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """Return sanitized tenant calendar events without persisting unmatched events."""
        conn = self._session.scalar(
            select(CRMCalendarConnection).where(
                CRMCalendarConnection.company_id == company_id,
                CRMCalendarConnection.provider == "google",
                CRMCalendarConnection.sync_status == "connected",
            )
        )
        if conn is None or self._cipher is None:
            return []
        settings = get_settings()
        provider = GoogleCalendarProvider(
            settings.google_calendar_client_id,
            settings.google_calendar_client_secret,
            settings.google_calendar_redirect_uri,
        )
        credentials = self._cipher.decrypt(conn.encrypted_credentials)
        try:
            try:
                events = await provider.list_events(credentials, start_time, end_time, conn.calendar_id)
            except CalendarProviderError as exc:
                refresh_token = credentials.get("refresh_token")
                if "401" not in str(exc) or not refresh_token:
                    raise
                refreshed = await provider.refresh_access_token(str(refresh_token))
                credentials = {**credentials, **refreshed, "refresh_token": refresh_token}
                conn.encrypted_credentials = self._cipher.encrypt(credentials)
                events = await provider.list_events(credentials, start_time, end_time, conn.calendar_id)
            conn.last_synced_at = datetime.now(timezone.utc)
            self._session.commit()
        except Exception as exc:
            self._session.rollback()
            raise CalendarProviderError("Lecture Google Calendar impossible.") from exc

        sanitized: list[dict[str, Any]] = []
        for event in events:
            start = self._google_event_datetime(event, "start")
            end = self._google_event_datetime(event, "end")
            if not event.get("id") or start is None or end is None or event.get("status") == "cancelled":
                continue
            sanitized.append({
                "external_event_id": str(event["id"]),
                "title": str(event.get("summary") or "Google Calendar"),
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                "duration_minutes": max(int((end - start).total_seconds() // 60), 1),
                "location": event.get("location"),
            })
        return sanitized

    async def _sync_to_external_calendar(
        self,
        company_id: UUID,
        appointment: CRMAppointment,
        client: CRMClient,
        action: str = "create",
    ) -> tuple[str, str | None]:
        """Synchronizes appointment action with connected Google Calendar if active."""
        conn = self._session.scalars(
            select(CRMCalendarConnection).where(
                CRMCalendarConnection.company_id == company_id,
                CRMCalendarConnection.sync_status == "connected",
            )
        ).first()

        if not conn or not self._cipher:
            return "not_configured", None

        if conn.sync_status == "error":
            return "failed", f"Le calendrier Google est en erreur ({conn.error_message or 'reconnexion requise'}). Veuillez reconnecter le calendrier."

        settings = get_settings()
        try:
            creds = self._cipher.decrypt(conn.encrypted_credentials)
            if conn.provider == "google":
                try:
                    provider = GoogleCalendarProvider(
                        settings.google_calendar_client_id,
                        settings.google_calendar_client_secret,
                        settings.google_calendar_redirect_uri,
                    )
                except TypeError:
                    provider = GoogleCalendarProvider()
                event_data = CalendarEventData(
                    title=appointment.title,
                    start_time=appointment.start_time,
                    end_time=appointment.end_time,
                    description=appointment.notes,
                    attendee_email=(
                        client.email.strip().lower()
                        if evaluate_crm_recipient(client, company_id, "email").allowed
                        else None
                    ),
                    client_name=client.full_name,
                )

                async def _perform_op(current_creds: dict[str, Any]):
                    if action == "create":
                        ext_id = await provider.create_event(current_creds, event_data, conn.calendar_id)
                        appointment.calendar_provider = "google"
                        appointment.external_event_id = ext_id
                        return "synced", None
                    elif action == "update" and appointment.external_event_id:
                        await provider.update_event(current_creds, appointment.external_event_id, event_data, conn.calendar_id)
                        return "synced", None
                    elif action == "delete" and appointment.external_event_id:
                        deleted = await provider.delete_event(current_creds, appointment.external_event_id, conn.calendar_id)
                        if not deleted:
                            return "failed", "Google Calendar n'a pas confirmé la suppression de l'événement."
                        appointment.external_event_id = None
                        return "synced", None
                    return "skipped", None

                try:
                    return await _perform_op(creds)
                except CalendarProviderError as exc:
                    cause = getattr(exc, "__cause__", None)
                    if getattr(cause, "code", None) == 401 and creds.get("refresh_token"):
                        try:
                            refreshed = await provider.refresh_access_token(str(creds["refresh_token"]))
                            creds = {**creds, **refreshed}
                            if hasattr(self._cipher, "encrypt"):
                                conn.encrypted_credentials = self._cipher.encrypt(creds)
                            conn.sync_status = "connected"
                            conn.error_message = None
                            self._session.commit()
                            return await _perform_op(creds)
                        except Exception as refresh_err:
                            conn.sync_status = "error"
                            conn.error_message = "Google token expired or revoked. Please reconnect."
                            self._session.commit()
                            return "failed", f"Synchronisation Google Calendar impossible (token expiré): {refresh_err}"
                    raise
        except Exception as exc:
            logger.warning(
                "CRM calendar synchronization failed",
                extra={"company_id": str(company_id), "appointment_id": str(appointment.id), "action": action},
            )
            return "failed", f"Synchronisation Google Calendar impossible: {exc}"

    # --- Services & Employees ---

    def list_services(self, company_id: UUID) -> list[CRMServiceModel]:
        return list(
            self._session.scalars(
                select(CRMServiceModel)
                .where(CRMServiceModel.company_id == company_id, CRMServiceModel.is_active.is_(True))
                .order_by(CRMServiceModel.name.asc())
            ).all()
        )

    def create_service(self, company_id: UUID, data: dict[str, Any]) -> CRMServiceModel:
        svc = CRMServiceModel(
            company_id=company_id,
            name=data["name"].strip(),
            description=data.get("description"),
            duration_minutes=data.get("duration_minutes", 60),
            price=data.get("price", 0.0),
            currency=data.get("currency", "CAD"),
            category=data.get("category"),
            color_hex=data.get("color_hex", "#0076FF"),
            buffer_before_minutes=data.get("buffer_before_minutes", 0),
            buffer_after_minutes=data.get("buffer_after_minutes", 0),
        )
        self._session.add(svc)
        self._session.commit()
        return svc

    def list_employees(self, company_id: UUID) -> list[CRMEmployee]:
        return list(
            self._session.scalars(
                select(CRMEmployee)
                .where(CRMEmployee.company_id == company_id, CRMEmployee.is_active.is_(True))
                .order_by(CRMEmployee.name.asc())
            ).all()
        )

    def create_employee(self, company_id: UUID, data: dict[str, Any]) -> CRMEmployee:
        emp = CRMEmployee(
            company_id=company_id,
            name=data["name"].strip(),
            email=data.get("email"),
            phone=data.get("phone"),
            role_title=data.get("role_title"),
            color_hex=data.get("color_hex", "#00D4FF"),
            working_hours=data.get("working_hours", {
                "monday": {"start": "09:00", "end": "17:00"},
                "tuesday": {"start": "09:00", "end": "17:00"},
                "wednesday": {"start": "09:00", "end": "17:00"},
                "thursday": {"start": "09:00", "end": "17:00"},
                "friday": {"start": "09:00", "end": "17:00"},
                "saturday": {"start": "09:00", "end": "16:00"},
            }),
        )
        self._session.add(emp)
        self._session.commit()
        return emp

    # --- Notes ---

    def create_note(self, company_id: UUID, data: dict[str, Any], author_name: str = "Système") -> CRMNote:
        note = CRMNote(
            company_id=company_id,
            client_id=data.get("client_id"),
            appointment_id=data.get("appointment_id"),
            author_name=author_name,
            content=data["content"].strip(),
            pinned=data.get("pinned", False),
        )
        self._session.add(note)
        self._session.commit()
        return note

    # --- Pipelines ---

    def list_pipelines(self, company_id: UUID) -> list[dict[str, Any]]:
        pipelines = list(
            self._session.scalars(
                select(CRMPipeline).where(CRMPipeline.company_id == company_id)
            ).all()
        )
        if not pipelines:
            # Create default pipeline if none exists
            default_p = CRMPipeline(company_id=company_id, name="Pipeline Commercial", is_default=True)
            self._session.add(default_p)
            self._session.flush()
            stages = [
                CRMPipelineStage(pipeline_id=default_p.id, name="Nouveau Lead", position=0, color_hex="#3B82F6", win_probability=0.1),
                CRMPipelineStage(pipeline_id=default_p.id, name="Contact Établi", position=1, color_hex="#6366F1", win_probability=0.25),
                CRMPipelineStage(pipeline_id=default_p.id, name="Proposition", position=2, color_hex="#8B5CF6", win_probability=0.5),
                CRMPipelineStage(pipeline_id=default_p.id, name="Négociation", position=3, color_hex="#F59E0B", win_probability=0.75),
                CRMPipelineStage(pipeline_id=default_p.id, name="Gagné", position=4, color_hex="#10B981", win_probability=1.0),
                CRMPipelineStage(pipeline_id=default_p.id, name="Perdu", position=5, color_hex="#EF4444", win_probability=0.0),
            ]
            self._session.add_all(stages)
            self._session.commit()
            pipelines = [default_p]

        results = []
        for p in pipelines:
            stages = list(
                self._session.scalars(
                    select(CRMPipelineStage)
                    .where(CRMPipelineStage.pipeline_id == p.id)
                    .order_by(CRMPipelineStage.position.asc())
                ).all()
            )
            opps = list(
                self._session.scalars(
                    select(CRMOpportunity).where(CRMOpportunity.company_id == company_id)
                ).all()
            )
            results.append({
                "id": str(p.id),
                "name": p.name,
                "stages": [
                    {
                        "id": str(s.id),
                        "name": s.name,
                        "position": s.position,
                        "color_hex": s.color_hex,
                        "win_probability": s.win_probability,
                        "opportunities": [
                            {
                                "id": str(o.id),
                                "title": o.title,
                                "company_name": o.company_name,
                                "amount": o.amount,
                                "currency": o.currency,
                                "stage": o.stage,
                                "probability": o.probability,
                            }
                            for o in opps
                            if o.stage.lower() == s.name.lower() or str(getattr(o, "stage_id", "")) == str(s.id)
                        ],
                    }
                    for s in stages
                ],
            })
        return results

    # --- Automations ---

    def list_automations(self, company_id: UUID) -> list[CRMAutomation]:
        autos = list(
            self._session.scalars(
                select(CRMAutomation).where(CRMAutomation.company_id == company_id)
            ).all()
        )
        if not autos:
            # Seed standard default automations
            default_rules = [
                CRMAutomation(
                    company_id=company_id,
                    name="Confirmation immédiate par Email",
                    trigger_type="appointment_created",
                    trigger_config={},
                    action_type="send_email",
                    action_config={"template": "appointment_confirmation"},
                    is_active=True,
                ),
                CRMAutomation(
                    company_id=company_id,
                    name="Rappel SMS 24h avant le rendez-vous",
                    trigger_type="appointment_approaching",
                    trigger_config={"hours_before": 24},
                    action_type="send_sms",
                    action_config={"template": "appointment_reminder"},
                    is_active=True,
                ),
                CRMAutomation(
                    company_id=company_id,
                    name="Relance client inactif depuis 45 jours",
                    trigger_type="client_inactive",
                    trigger_config={"days_inactive": 45},
                    action_type="send_email",
                    action_config={"template": "we_miss_you"},
                    is_active=True,
                ),
            ]
            self._session.add_all(default_rules)
            self._session.commit()
            autos = default_rules
        return autos

    def toggle_automation(self, company_id: UUID, automation_id: UUID) -> bool:
        auto = self._session.scalars(
            select(CRMAutomation).where(
                CRMAutomation.id == automation_id,
                CRMAutomation.company_id == company_id,
            )
        ).first()
        if not auto:
            return False
        auto.is_active = not auto.is_active
        self._session.commit()
        return auto.is_active

    # --- Calendar Connections ---

    def get_calendar_connection(self, company_id: UUID) -> CRMCalendarConnection | None:
        return self._session.scalars(
            select(CRMCalendarConnection).where(CRMCalendarConnection.company_id == company_id)
        ).first()

    def disconnect_calendar(self, company_id: UUID) -> bool:
        conn = self.get_calendar_connection(company_id)
        if not conn:
            return False
        conn.sync_status = "disconnected"
        self._session.commit()
        return True

    # --- Audit Logger ---

    def _log_activity(
        self,
        company_id: UUID,
        entity_type: str,
        entity_id: UUID,
        action: str,
        actor_name: str,
        details: dict[str, Any],
    ) -> None:
        clean_details: dict[str, Any] = {}
        if isinstance(details, dict):
            for k, v in details.items():
                if isinstance(v, (datetime, date)):
                    clean_details[k] = v.isoformat()
                elif isinstance(v, UUID):
                    clean_details[k] = str(v)
                else:
                    clean_details[k] = v
        else:
            clean_details = details or {}

        log = CRMActivityLog(
            company_id=company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_name=actor_name,
            details=clean_details,
        )
        self._session.add(log)
