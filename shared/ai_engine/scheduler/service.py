from datetime import datetime
from typing import Protocol

from shared.ai_engine.jobs.models import AIEngineJob


class JobScheduler(Protocol):
    """Port qui sera implémenté par le planificateur Enterprise choisi."""

    def enqueue(self, job: AIEngineJob) -> str: ...

    def schedule(self, job: AIEngineJob, run_at: datetime) -> str: ...
