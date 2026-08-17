from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol

from shared.ai_engine.contracts import TenantContext


@dataclass(frozen=True, slots=True)
class MonitoringEvent:
    tenant: TenantContext
    event_type: str
    occurred_at: datetime
    attributes: Mapping[str, Any]


class MonitoringSink(Protocol):
    def record(self, event: MonitoringEvent) -> None: ...
