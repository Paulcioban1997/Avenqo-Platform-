"""Availability and scheduling conflict engine for Avenqo CRM AI."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from backend.app.models.crm import (
    CRMAppointment,
    CRMCalendarConnection,
    CRMEmployee,
    CRMService,
)
from backend.app.services.calendar.base import BusySlot
from backend.app.services.calendar.google_provider import GoogleCalendarProvider
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher


class CRMAvailabilityService:
    """Calculates available appointment slots and validates conflicts across CRM and external calendars."""

    def __init__(self, session: Session, cipher: ConnectorSecretCipher | None = None) -> None:
        self._session = session
        self._cipher = cipher

    def check_conflict(
        self,
        company_id: UUID,
        start_time: datetime,
        end_time: datetime,
        employee_id: UUID | None = None,
        exclude_appointment_id: UUID | None = None,
    ) -> tuple[bool, str | None]:
        """Verifies if the requested appointment window conflicts with existing active appointments.

        Returns (True, reason) if a conflict exists, (False, None) if free.
        """
        if start_time >= end_time:
            return True, "L'heure de début doit précéder l'heure de fin."

        # Filter active appointments for the company (and specific employee if assigned)
        query = select(CRMAppointment).where(
            CRMAppointment.company_id == company_id,
            CRMAppointment.is_deleted.is_(False),
            CRMAppointment.status.in_(["confirmed", "pending"]),
            and_(
                CRMAppointment.start_time < end_time,
                CRMAppointment.end_time > start_time,
            ),
        )
        if employee_id is not None:
            query = query.where(
                (CRMAppointment.employee_id == employee_id) | (CRMAppointment.employee_id.is_(None))
            )
        if exclude_appointment_id is not None:
            query = query.where(CRMAppointment.id != exclude_appointment_id)

        conflicting = self._session.scalars(query).first()
        if conflicting:
            c_start = conflicting.start_time.strftime("%H:%M")
            c_end = conflicting.end_time.strftime("%H:%M")
            return True, f"Conflit de créneau avec un rendez-vous existant ({conflicting.title} de {c_start} à {c_end})."

        return False, None

    async def list_available_slots(
        self,
        company_id: UUID,
        target_date: date | datetime,
        service_id: UUID | None = None,
        employee_id: UUID | None = None,
        duration_minutes: int = 60,
        slot_interval_minutes: int = 30,
    ) -> list[dict[str, Any]]:
        """Computes bookable slots for a given day taking employee schedules, CRM appointments and Google Calendar into account."""
        if isinstance(target_date, datetime):
            target_date = target_date.date()

        # 1. Determine duration & buffers
        buffer_before = 0
        buffer_after = 0
        if service_id:
            svc = self._session.get(CRMService, service_id)
            if svc and svc.company_id == company_id and svc.is_active:
                duration_minutes = svc.duration_minutes
                buffer_before = svc.buffer_before_minutes
                buffer_after = svc.buffer_after_minutes
                duration_minutes = svc.duration_minutes
                buffer_before = svc.buffer_before_minutes
                buffer_after = svc.buffer_after_minutes

        # 2. Determine working hours for the target day
        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        weekday_name = day_names[target_date.weekday()]

        work_start = time(9, 0)
        work_end = time(18, 0)
        is_day_off = target_date.weekday() == 6  # Sunday off by default

        emp_obj: CRMEmployee | None = None
        if employee_id:
            emp = self._session.get(CRMEmployee, employee_id)
            if emp and emp.company_id == company_id and emp.is_active:
                emp_obj = emp
                sched = emp.working_hours.get(weekday_name) if emp.working_hours else None
                if sched:
                    if isinstance(sched, dict) and "start" in sched and "end" in sched:
                        sh, sm = map(int, sched["start"].split(":"))
                        eh, em = map(int, sched["end"].split(":"))
                        work_start = time(sh, sm)
                        work_end = time(eh, em)
                        is_day_off = False
                    elif isinstance(sched, list) and len(sched) > 0:
                        first_shift = sched[0]
                        sh, sm = map(int, first_shift["start"].split(":"))
                        eh, em = map(int, first_shift["end"].split(":"))
                        work_start = time(sh, sm)
                        work_end = time(eh, em)
                        is_day_off = False
                elif emp.working_hours and weekday_name not in emp.working_hours:
                    is_day_off = True

        if is_day_off:
            return []

        day_start_dt = datetime.combine(target_date, work_start, tzinfo=timezone.utc)
        day_end_dt = datetime.combine(target_date, work_end, tzinfo=timezone.utc)

        # 3. Load active CRM appointments on that day
        day_bounds_start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
        day_bounds_end = datetime.combine(target_date, time.max, tzinfo=timezone.utc)

        apt_query = select(CRMAppointment).where(
            CRMAppointment.company_id == company_id,
            CRMAppointment.is_deleted.is_(False),
            CRMAppointment.status.in_(["confirmed", "pending"]),
            CRMAppointment.start_time >= day_bounds_start,
            CRMAppointment.start_time <= day_bounds_end,
        )
        if employee_id:
            apt_query = apt_query.where(
                (CRMAppointment.employee_id == employee_id) | (CRMAppointment.employee_id.is_(None))
            )
        active_appointments = list(self._session.scalars(apt_query).all())

        # 4. Query external calendar busy slots if connected
        external_busy: list[BusySlot] = []
        conn = self._session.scalars(
            select(CRMCalendarConnection).where(
                CRMCalendarConnection.company_id == company_id,
                CRMCalendarConnection.sync_status == "connected",
            )
        ).first()

        if conn and self._cipher:
            try:
                creds = self._cipher.decrypt(conn.encrypted_credentials)
                if conn.provider == "google":
                    provider = GoogleCalendarProvider()
                    external_busy = await provider.check_busy_slots(
                        creds, day_bounds_start, day_bounds_end, conn.calendar_id
                    )
            except Exception:
                pass  # Fallback gracefully to internal availability

        # 5. Generate and test candidate slots
        available_slots: list[dict[str, Any]] = []
        curr_dt = day_start_dt
        total_duration = timedelta(minutes=duration_minutes + buffer_before + buffer_after)
        step = timedelta(minutes=slot_interval_minutes)

        while curr_dt + timedelta(minutes=duration_minutes) <= day_end_dt:
            slot_start = curr_dt + timedelta(minutes=buffer_before)
            slot_end = slot_start + timedelta(minutes=duration_minutes)

            # Check overlap with existing appointments
            has_apt_conflict = False
            for apt in active_appointments:
                apt_start = apt.start_time if apt.start_time.tzinfo else apt.start_time.replace(tzinfo=timezone.utc)
                apt_end = apt.end_time if apt.end_time.tzinfo else apt.end_time.replace(tzinfo=timezone.utc)
                if slot_start < apt_end and slot_end > apt_start:
                    has_apt_conflict = True
                    break

            # Check overlap with external busy slots
            has_ext_conflict = False
            for busy in external_busy:
                busy_start = busy.start_time if busy.start_time.tzinfo else busy.start_time.replace(tzinfo=timezone.utc)
                busy_end = busy.end_time if busy.end_time.tzinfo else busy.end_time.replace(tzinfo=timezone.utc)
                if slot_start < busy_end and slot_end > busy_start:
                    has_ext_conflict = True
                    break

            if not has_apt_conflict and not has_ext_conflict:
                available_slots.append({
                    "start_time": slot_start.isoformat(),
                    "end_time": slot_end.isoformat(),
                    "display_time": f"{slot_start.strftime('%H:%M')} - {slot_end.strftime('%H:%M')}",
                    "employee_id": str(emp_obj.id) if emp_obj else None,
                    "employee_name": emp_obj.name if emp_obj else "Disponible",
                    "duration_minutes": duration_minutes,
                })

            curr_dt += step

        return available_slots
