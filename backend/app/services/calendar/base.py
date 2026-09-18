"""Calendar provider abstraction for Avenqo CRM AI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class CalendarEventData:
    title: str
    start_time: datetime
    end_time: datetime
    description: str | None = None
    location: str | None = None
    attendee_email: str | None = None
    client_name: str | None = None


@dataclass(frozen=True, slots=True)
class BusySlot:
    start_time: datetime
    end_time: datetime


class CalendarProviderError(Exception):
    """Base error for external calendar provider interactions."""
    pass


class CalendarProvider(ABC):
    """Abstract interface supporting multi-provider calendar integration."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the calendar provider (e.g. 'google', 'outlook')."""
        ...

    @abstractmethod
    def get_auth_url(self, state: str, redirect_uri: str | None = None) -> str:
        """Generates OAuth consent URL."""
        ...

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str | None = None) -> dict[str, Any]:
        """Exchanges authorization code for token payload."""
        ...

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refreshes expired access token."""
        ...

    @abstractmethod
    async def list_events(
        self,
        credentials: dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        calendar_id: str = "primary",
    ) -> list[dict[str, Any]]:
        """Reads external calendar events."""
        ...

    @abstractmethod
    async def create_event(
        self,
        credentials: dict[str, Any],
        event: CalendarEventData,
        calendar_id: str = "primary",
    ) -> str:
        """Creates event in external calendar and returns external event ID."""
        ...

    @abstractmethod
    async def update_event(
        self,
        credentials: dict[str, Any],
        external_event_id: str,
        event: CalendarEventData,
        calendar_id: str = "primary",
    ) -> bool:
        """Updates event in external calendar."""
        ...

    @abstractmethod
    async def delete_event(
        self,
        credentials: dict[str, Any],
        external_event_id: str,
        calendar_id: str = "primary",
    ) -> bool:
        """Deletes/cancels event in external calendar."""
        ...

    @abstractmethod
    async def check_busy_slots(
        self,
        credentials: dict[str, Any],
        start_time: datetime,
        end_time: datetime,
        calendar_id: str = "primary",
    ) -> list[BusySlot]:
        """Queries free/busy slots to prevent double-booking."""
        ...
