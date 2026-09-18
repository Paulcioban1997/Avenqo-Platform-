"""Core business service for Avenqo CRM AI operations and tenant data management."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

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
from backend.app.services.calendar.base import CalendarEventData
from backend.app.services.calendar.google_provider import GoogleCalendarProvider
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher
from backend.app.services.crm_availability_service import CRMAvailabilityService


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
        start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        if now.month == 12:
            start_of_next_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            start_of_next_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

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

    def create_client(self, company_id: UUID, data: dict[str, Any], actor_name: str = "Utilisateur") -> CRMClient:
        client = CRMClient(
            company_id=company_id,
            first_name=data["first_name"].strip(),
            last_name=data["last_name"].strip(),
            email=data["email"].strip().lower(),
            phone=data.get("phone", "").strip() or None,
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

    def update_client(self, company_id: UUID, client_id: UUID, data: dict[str, Any], actor_name: str = "Utilisateur") -> CRMClient | None:
        client = self.get_client(company_id, client_id)
        if not client:
            return None

        for field in ["first_name", "last_name", "email", "phone", "company_name", "industry_type", "status"]:
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
    ) -> list[dict[str, Any]]:
        query = select(CRMAppointment).where(
            CRMAppointment.company_id == company_id,
            CRMAppointment.is_deleted.is_(False),
        )
        if start_date:
            query = query.where(CRMAppointment.start_time >= start_date)
        if end_date:
            query = query.where(CRMAppointment.end_time <= end_date)
        if status:
            query = query.where(CRMAppointment.status == status)
        if employee_id:
            query = query.where(CRMAppointment.employee_id == employee_id)
        if client_id:
            query = query.where(CRMAppointment.client_id == client_id)

        query = query.order_by(CRMAppointment.start_time.asc())
        apts = list(self._session.scalars(query).all())

        results = []
        for a in apts:
            client = self._session.get(CRMClient, a.client_id)
            service = self._session.get(CRMServiceModel, a.service_id) if a.service_id else None
            employee = self._session.get(CRMEmployee, a.employee_id) if a.employee_id else None

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
        start_time = data["start_time"]
        duration = data.get("duration_minutes", 60)
        end_time = data.get("end_time") or (start_time + timedelta(minutes=duration))
        employee_id = data.get("employee_id")

        if check_conflicts:
            has_conflict, reason = self._availability.check_conflict(
                company_id, start_time, end_time, employee_id
            )
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
            industry_data=data.get("industry_data", {}),
        )
        self._session.add(appointment)
        self._session.flush()

        # External Calendar Sync (Google Calendar)
        await self._sync_to_external_calendar(company_id, appointment, client, action="create")

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

    async def update_appointment(
        self,
        company_id: UUID,
        appointment_id: UUID,
        data: dict[str, Any],
        actor_name: str = "Utilisateur",
        check_conflicts: bool = True,
    ) -> tuple[CRMAppointment | None, str | None]:
        apt = self._session.scalars(
            select(CRMAppointment).where(
                CRMAppointment.id == appointment_id,
                CRMAppointment.company_id == company_id,
                CRMAppointment.is_deleted.is_(False),
            )
        ).first()
        if not apt:
            return None, "Rendez-vous introuvable."

        start_time = data.get("start_time", apt.start_time)
        duration = data.get("duration_minutes", apt.duration_minutes)
        end_time = data.get("end_time") or (start_time + timedelta(minutes=duration))
        emp_id = data.get("employee_id", apt.employee_id)

        if check_conflicts and ("start_time" in data or "employee_id" in data or "duration_minutes" in data):
            has_conflict, reason = self._availability.check_conflict(
                company_id, start_time, end_time, emp_id, exclude_appointment_id=appointment_id
            )
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
            await self._sync_to_external_calendar(company_id, apt, client, action="update")

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
        apt = self._session.scalars(
            select(CRMAppointment).where(
                CRMAppointment.id == appointment_id,
                CRMAppointment.company_id == company_id,
            )
        ).first()
        if not apt:
            return False

        apt.status = "cancelled"

        client = self.get_client(company_id, apt.client_id)
        if client:
            await self._sync_to_external_calendar(company_id, apt, client, action="delete")

        self._log_activity(
            company_id,
            entity_type="appointment",
            entity_id=apt.id,
            action="cancel",
            actor_name=actor_name,
            details={"status": "cancelled"},
        )
        self._session.commit()
        return True

    # --- External Calendar Sync Helper ---

    async def _sync_to_external_calendar(
        self,
        company_id: UUID,
        appointment: CRMAppointment,
        client: CRMClient,
        action: str = "create",
    ) -> None:
        """Synchronizes appointment action with connected Google Calendar if active."""
        conn = self._session.scalars(
            select(CRMCalendarConnection).where(
                CRMCalendarConnection.company_id == company_id,
                CRMCalendarConnection.sync_status == "connected",
            )
        ).first()

        if not conn or not self._cipher:
            return

        try:
            creds = self._cipher.decrypt(conn.encrypted_credentials)
            if conn.provider == "google":
                provider = GoogleCalendarProvider()
                event_data = CalendarEventData(
                    title=appointment.title,
                    start_time=appointment.start_time,
                    end_time=appointment.end_time,
                    description=appointment.notes,
                    attendee_email=client.email,
                    client_name=client.full_name,
                )
                if action == "create":
                    ext_id = await provider.create_event(creds, event_data, conn.calendar_id)
                    appointment.calendar_provider = "google"
                    appointment.external_event_id = ext_id
                elif action == "update" and appointment.external_event_id:
                    await provider.update_event(creds, appointment.external_event_id, event_data, conn.calendar_id)
                elif action == "delete" and appointment.external_event_id:
                    await provider.delete_event(creds, appointment.external_event_id, conn.calendar_id)
                    appointment.external_event_id = None
        except Exception:
            pass  # Avoid aborting CRM operations if external sync temporarily errors

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
        log = CRMActivityLog(
            company_id=company_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_name=actor_name,
            details=details,
        )
        self._session.add(log)
