from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True, slots=True)
class DataFreshness:
    source: str | None
    last_updated_at: datetime | None
    queried_at: datetime
    freshness_status: str
    age_seconds: int | None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class DataFreshnessService:
    """Classify freshness only from timestamps that the connector can prove."""

    def __init__(
        self,
        *,
        stale_after: timedelta = timedelta(minutes=15),
        near_realtime_after: timedelta = timedelta(minutes=2),
        near_realtime_max_age: timedelta = timedelta(minutes=5),
    ) -> None:
        self._stale_after = stale_after
        self._near_realtime_after = near_realtime_after
        self._near_realtime_max_age = near_realtime_max_age

    def evaluate(
        self,
        *,
        source: str | None,
        last_updated_at: datetime | None,
        queried_at: datetime | None = None,
        source_available: bool = True,
        live_query_succeeded: bool = False,
        event_received_at: datetime | None = None,
    ) -> DataFreshness:
        queried = self._utc(queried_at or datetime.now(timezone.utc))
        updated = self._utc(last_updated_at) if last_updated_at is not None else None
        event_received = self._utc(event_received_at) if event_received_at is not None else None

        if not source_available or not source:
            return DataFreshness(source, updated, queried, "UNAVAILABLE", None)
        if live_query_succeeded:
            return DataFreshness(source, updated or queried, queried, "LIVE", 0)
        if updated is None:
            return DataFreshness(source, None, queried, "UNAVAILABLE", None)

        age = queried - updated
        if age < timedelta(0):
            return DataFreshness(source, updated, queried, "UNAVAILABLE", None)
        age_seconds = int(age.total_seconds())

        if event_received is not None:
            processing_delay = updated - event_received
            event_age = queried - event_received
            if (
                timedelta(0) <= processing_delay <= self._near_realtime_after
                and timedelta(0) <= event_age <= self._near_realtime_max_age
            ):
                return DataFreshness(source, updated, queried, "NEAR_REALTIME", age_seconds)

        state = "STALE" if age > self._stale_after else "SYNCED"
        return DataFreshness(source, updated, queried, state, age_seconds)

    def for_snapshot(self, snapshot, *, queried_at: datetime | None = None) -> DataFreshness:
        source = (
            snapshot.active_source_provider
            or snapshot.active_source_name
            or snapshot.active_source_type
        )
        available = (
            snapshot.active_source_selected
            and snapshot.status not in {"source_unavailable", "no_data", "error", "processing"}
            and bool(snapshot.prepared or snapshot.retail_summaries)
        )
        return self.evaluate(
            source=source,
            last_updated_at=snapshot.active_source_last_updated_at,
            event_received_at=getattr(snapshot, "active_source_last_event_received_at", None),
            queried_at=queried_at,
            source_available=available,
        )

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)