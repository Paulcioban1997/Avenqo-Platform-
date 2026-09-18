"""Calendar provider package for Avenqo CRM AI."""

from backend.app.services.calendar.base import (
    BusySlot,
    CalendarEventData,
    CalendarProvider,
    CalendarProviderError,
)
from backend.app.services.calendar.google_provider import GoogleCalendarProvider
from backend.app.services.calendar.outlook_provider import OutlookCalendarProvider

__all__ = [
    "BusySlot",
    "CalendarEventData",
    "CalendarProvider",
    "CalendarProviderError",
    "GoogleCalendarProvider",
    "OutlookCalendarProvider",
]
