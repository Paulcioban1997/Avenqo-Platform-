"""Canonical tenant scheduling reads shared by CRM, Copilot and Voice."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config.settings import get_settings
from backend.app.models.company import Company
from backend.app.models.crm import CRMAppointment, CRMCalendarConnection, CRMEmployee, CRMService
from backend.app.models.voice import VoiceBusinessConfig
from backend.app.services.calendar.base import BusySlot, CalendarProviderError
from backend.app.services.calendar.google_provider import GoogleCalendarProvider
from backend.app.services.connector_secret_cipher import ConnectorSecretCipher


class AvailabilityUnavailable(CalendarProviderError):
    pass


class CRMAvailabilityService:
    def __init__(self, session: Session, cipher: ConnectorSecretCipher | None = None) -> None:
        self._session = session
        self._cipher = cipher

    def _zone(self, company_id: UUID) -> ZoneInfo:
        company = self._session.get(Company, company_id)
        tz_name = (company.timezone if company and company.timezone else None)
        if not tz_name:
            config = self._session.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id))
            tz_name = (config.timezone_name if config and config.timezone_name else None)
        if not tz_name:
            tz_name = "America/Montreal"
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return ZoneInfo("UTC")

    def normalize(self, company_id: UUID, value: datetime) -> datetime:
        zone = self._zone(company_id)
        if value.tzinfo is None:
            local = value.replace(tzinfo=zone)
            roundtrip = local.astimezone(timezone.utc).astimezone(zone)
            if roundtrip.replace(tzinfo=None) != value or local.utcoffset() != value.replace(tzinfo=zone, fold=1).utcoffset():
                raise AvailabilityUnavailable("AMBIGUOUS_OR_NONEXISTENT_LOCAL_TIME")
            value = local
        return value.astimezone(timezone.utc)

    def _resource(self, model, company_id: UUID, resource_id: UUID | None):
        if resource_id is None:
            return None
        resource = self._session.get(model, resource_id)
        if resource is None or resource.company_id != company_id or not resource.is_active:
            raise AvailabilityUnavailable("RESOURCE_NOT_AUTHORIZED")
        return resource

    def check_conflict(self, company_id: UUID, start_time: datetime, end_time: datetime,
                       employee_id: UUID | None = None, exclude_appointment_id: UUID | None = None) -> tuple[bool, str | None]:
        start_time = self.normalize(company_id, start_time)
        end_time = self.normalize(company_id, end_time)
        self._resource(CRMEmployee, company_id, employee_id)
        if start_time >= end_time:
            return True, "INVALID_INTERVAL"
        services = {service.id: service for service in self._session.scalars(select(CRMService).where(CRMService.company_id == company_id)).all()}
        max_before = max((service.buffer_before_minutes for service in services.values()), default=0)
        max_after = max((service.buffer_after_minutes for service in services.values()), default=0)
        query = select(CRMAppointment).where(
            CRMAppointment.company_id == company_id,
            CRMAppointment.is_deleted.is_(False),
            CRMAppointment.status.in_(("confirmed", "pending", "blocked")),
            CRMAppointment.start_time < end_time + timedelta(minutes=max_before),
            CRMAppointment.end_time > start_time - timedelta(minutes=max_after),
        )
        if employee_id is not None:
            query = query.where((CRMAppointment.employee_id == employee_id) | CRMAppointment.employee_id.is_(None))
        if exclude_appointment_id is not None:
            query = query.where(CRMAppointment.id != exclude_appointment_id)
        for appointment in self._session.scalars(query).all():
            service = services.get(appointment.service_id) if appointment.service_id is not None else None
            opened = appointment.start_time.replace(tzinfo=timezone.utc) if appointment.start_time.tzinfo is None else appointment.start_time.astimezone(timezone.utc)
            closed = appointment.end_time.replace(tzinfo=timezone.utc) if appointment.end_time.tzinfo is None else appointment.end_time.astimezone(timezone.utc)
            opened -= timedelta(minutes=service.buffer_before_minutes if service else 0)
            closed += timedelta(minutes=service.buffer_after_minutes if service else 0)
            if start_time < closed and end_time > opened:
                return True, "Conflit CRM_BUSY"
        return False, None

    async def _external_busy(self, company_id: UUID, start: datetime, end: datetime) -> list[BusySlot]:
        connections = self._session.scalars(select(CRMCalendarConnection).where(
            CRMCalendarConnection.company_id == company_id,
            CRMCalendarConnection.provider == "google",
            CRMCalendarConnection.sync_status != "disconnected",
        )).all()
        if not connections:
            return []
        try:
            settings = get_settings()
            cipher = self._cipher or ConnectorSecretCipher(settings.connector_encryption_keys)
            try:
                provider = GoogleCalendarProvider(
                    settings.google_calendar_client_id,
                    settings.google_calendar_client_secret,
                    settings.google_calendar_redirect_uri,
                )
            except TypeError:
                provider = GoogleCalendarProvider()
            busy = []
            for connection in connections:
                if connection.sync_status == "error":
                    raise AvailabilityUnavailable(f"EXTERNAL_CALENDAR_ERROR: {connection.error_message or 'Google Calendar token expired. Please reconnect.'}")
                if connection.sync_status != "connected":
                    raise AvailabilityUnavailable("EXTERNAL_AVAILABILITY_UNAVAILABLE")
                credentials = cipher.decrypt(connection.encrypted_credentials)
                try:
                    periods = await provider.check_busy_slots(credentials, start, end, connection.calendar_id)
                except CalendarProviderError as exc:
                    cause = getattr(exc, "__cause__", None)
                    if getattr(cause, "code", None) != 401 or not credentials.get("refresh_token"):
                        raise
                    try:
                        refreshed = await provider.refresh_access_token(str(credentials["refresh_token"]))
                        credentials = {**credentials, **refreshed}
                        if hasattr(cipher, "encrypt"):
                            connection.encrypted_credentials = cipher.encrypt(credentials)
                        connection.sync_status = "connected"
                        connection.error_message = None
                        self._session.commit()
                        periods = await provider.check_busy_slots(credentials, start, end, connection.calendar_id)
                    except Exception as refresh_exc:
                        connection.sync_status = "error"
                        connection.error_message = "Google token expired or revoked. Please reconnect."
                        self._session.commit()
                        raise AvailabilityUnavailable("EXTERNAL_AVAILABILITY_UNAVAILABLE") from refresh_exc
                busy.extend(periods)
            return busy
        except AvailabilityUnavailable:
            raise
        except Exception as exc:
            raise AvailabilityUnavailable("EXTERNAL_AVAILABILITY_UNAVAILABLE") from exc

    def _windows(self, company_id: UUID, day: date, employee_id: UUID | None = None) -> list[tuple[datetime, datetime]]:
        zone = self._zone(company_id)
        employee = self._resource(CRMEmployee, company_id, employee_id)
        config = self._session.scalar(select(VoiceBusinessConfig).where(VoiceBusinessConfig.company_id == company_id))
        company = self._session.get(Company, company_id)
        schedule = (company.business_hours if company else None) or {}
        weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[day.weekday()]
        if schedule:
            records = schedule.get("date_overrides", {}).get(day.isoformat(), schedule.get("weekly", {}).get(weekday, []))
        elif config and config.opening_hours:
            records = [config.opening_hours[weekday]] if weekday in config.opening_hours else []
            if config.timezone_name and config.timezone_name != zone.key:
                try:
                    cfg_zone = ZoneInfo(config.timezone_name)
                    if cfg_zone.utcoffset(datetime.now(timezone.utc)) == zone.utcoffset(datetime.now(timezone.utc)):
                        zone = cfg_zone
                    else:
                        raise AvailabilityUnavailable("BUSINESS_TIMEZONE_MISMATCH")
                except AvailabilityUnavailable:
                    raise
                except Exception:
                    pass
        else:
            if weekday in {"monday", "tuesday", "wednesday", "thursday", "friday"}:
                records = [{"open": "09:00", "close": "17:00"}]
            else:
                records = []
        if not records:
            return []
        def interval(record, start_key, end_key):
            start = self.normalize(company_id, datetime.combine(day, time.fromisoformat(record[start_key])))
            end = self.normalize(company_id, datetime.combine(day, time.fromisoformat(record[end_key])))
            if start >= end:
                raise AvailabilityUnavailable("INVALID_WORKING_HOURS")
            return start, end
        try:
            business_windows = [interval(record, "open", "close") for record in records]
            if employee is None:
                return business_windows
            shifts = employee.working_hours.get(weekday)
            if not shifts:
                return []
            shifts = shifts if isinstance(shifts, list) else [shifts]
            windows = []
            for shift in shifts:
                staff_start, staff_end = interval(shift, "start", "end")
                for business_start, business_end in business_windows:
                    start, end = max(business_start, staff_start), min(business_end, staff_end)
                    if start < end:
                        windows.append((start, end))
            return windows
        except AvailabilityUnavailable:
            raise
        except Exception as exc:
            raise AvailabilityUnavailable("INVALID_WORKING_HOURS") from exc

    async def check_combined_conflict(self, company_id: UUID, start_time: datetime, end_time: datetime,
                                      employee_id: UUID | None = None, exclude_appointment_id: UUID | None = None) -> tuple[bool, str | None]:
        start = self.normalize(company_id, start_time)
        end = self.normalize(company_id, end_time)
        conflict, reason = self.check_conflict(company_id, start, end, employee_id, exclude_appointment_id)
        if conflict:
            return conflict, reason
        busy = await self._external_busy(company_id, start, end)
        if any(start < period.end_time.astimezone(timezone.utc) and end > period.start_time.astimezone(timezone.utc) for period in busy):
            return True, "GOOGLE_BUSY"
        return False, None

    async def check_booking_conflict(self, company_id: UUID, start_time: datetime, end_time: datetime,
                                     employee_id: UUID | None = None, service_id: UUID | None = None,
                                     exclude_appointment_id: UUID | None = None) -> tuple[bool, str | None]:
        start = self.normalize(company_id, start_time)
        end = self.normalize(company_id, end_time)
        if start >= end:
            return True, "INVALID_INTERVAL"
        service = self._resource(CRMService, company_id, service_id)
        padded_start = start - timedelta(minutes=service.buffer_before_minutes if service else 0)
        padded_end = end + timedelta(minutes=service.buffer_after_minutes if service else 0)
        windows = self._windows(company_id, start.astimezone(self._zone(company_id)).date(), employee_id)
        if not any(padded_start >= opened and padded_end <= closed for opened, closed in windows):
            return True, "OUTSIDE_WORKING_HOURS"
        return await self.check_combined_conflict(company_id, padded_start, padded_end, employee_id, exclude_appointment_id)

    async def check_availability(self, company_id: UUID, start_time: datetime, duration_minutes: int = 60,
                                 employee_id: UUID | None = None, service_id: UUID | None = None) -> dict[str, Any]:
        try:
            if not 1 <= duration_minutes <= 480:
                raise AvailabilityUnavailable("INVALID_DURATION")
            start = self.normalize(company_id, start_time)
            if start <= datetime.now(timezone.utc):
                return {"available": False, "state": "BUSY", "reason": "PAST_INTERVAL"}
            service = self._resource(CRMService, company_id, service_id)
            duration = service.duration_minutes if service else duration_minutes
            end = start + timedelta(minutes=duration)
            padded_start = start - timedelta(minutes=service.buffer_before_minutes if service else 0)
            padded_end = end + timedelta(minutes=service.buffer_after_minutes if service else 0)
            windows = self._windows(company_id, start.astimezone(self._zone(company_id)).date(), employee_id)
            if not any(padded_start >= opened and padded_end <= closed for opened, closed in windows):
                target_date = start.astimezone(self._zone(company_id)).date()
                suggested = await self.list_available_slots(company_id, target_date, service_id=service_id, employee_id=employee_id, duration_minutes=duration)
                return {
                    "available": False, "state": "BUSY", "reason": "OUTSIDE_WORKING_HOURS",
                    "suggested_slots": [s["start_time"] for s in suggested[:3]],
                    "start_time": start.astimezone(self._zone(company_id)).isoformat(),
                    "end_time": end.astimezone(self._zone(company_id)).isoformat(),
                }
            conflict, reason = await self.check_combined_conflict(company_id, padded_start, padded_end, employee_id)
            suggested_slots = []
            if conflict:
                target_date = start.astimezone(self._zone(company_id)).date()
                suggested = await self.list_available_slots(company_id, target_date, service_id=service_id, employee_id=employee_id, duration_minutes=duration)
                suggested_slots = [s["start_time"] for s in suggested[:3]]
            return {"available": not conflict, "state": "BUSY" if conflict else "AVAILABLE", "reason": reason,
                    "suggested_slots": suggested_slots,
                    "start_time": start.astimezone(self._zone(company_id)).isoformat(),
                    "end_time": end.astimezone(self._zone(company_id)).isoformat()}
        except AvailabilityUnavailable as exc:
            return {"available": False, "state": str(exc), "reason": str(exc)}

    async def list_available_slots(self, company_id: UUID, target_date: date | datetime,
                                   service_id: UUID | None = None, employee_id: UUID | None = None,
                                   duration_minutes: int = 60, slot_interval_minutes: int = 30) -> list[dict[str, Any]]:
        zone = self._zone(company_id)
        if isinstance(target_date, datetime):
            target_date = self.normalize(company_id, target_date).astimezone(zone).date()
        if not 1 <= duration_minutes <= 480 or not 1 <= slot_interval_minutes <= 480:
            raise AvailabilityUnavailable("INVALID_DURATION")
        service = self._resource(CRMService, company_id, service_id)
        employee = self._resource(CRMEmployee, company_id, employee_id)
        duration_minutes = service.duration_minutes if service else duration_minutes
        before = timedelta(minutes=service.buffer_before_minutes if service else 0)
        after = timedelta(minutes=service.buffer_after_minutes if service else 0)
        windows = self._windows(company_id, target_date, employee_id)
        if not windows:
            return []
        busy = await self._external_busy(company_id, min(window[0] for window in windows), max(window[1] for window in windows))
        slots = {}
        for opened, closed in windows:
            cursor = opened + before
            while cursor + timedelta(minutes=duration_minutes) + after <= closed:
                end = cursor + timedelta(minutes=duration_minutes)
                padded_start, padded_end = cursor - before, end + after
                conflict, _ = self.check_conflict(company_id, padded_start, padded_end, employee_id)
                if cursor > datetime.now(timezone.utc) and not conflict and not any(padded_start < period.end_time and padded_end > period.start_time for period in busy):
                    local_start, local_end = cursor.astimezone(zone), end.astimezone(zone)
                    slots[cursor] = {"start_time": local_start.isoformat(), "end_time": local_end.isoformat(),
                                     "display_time": f"{local_start:%H:%M} - {local_end:%H:%M}",
                                     "employee_id": str(employee_id) if employee_id else None,
                                     "employee_name": employee.name if employee else None,
                                     "duration_minutes": duration_minutes}
                cursor += timedelta(minutes=slot_interval_minutes)
        return [slots[key] for key in sorted(slots)]