from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping
from uuid import UUID, uuid4

from shared.ai_engine.contracts import TenantContext


class JobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class AIEngineJob:
    tenant: TenantContext
    module_code: str
    task_code: str
    job_type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    state: JobState = JobState.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
