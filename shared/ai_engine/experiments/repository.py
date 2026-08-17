"""Contrat de persistance des historiques d'entraînement."""

from typing import Protocol, Sequence
from uuid import UUID

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.experiments.models import ExperimentRun


class ExperimentRepository(Protocol):
    """Stocke et consulte les Runs sans imposer une base de données."""

    def save(self, run: ExperimentRun) -> None: ...

    def get(self, tenant: TenantContext, run_id: UUID) -> ExperimentRun | None: ...

    def list_for_task(
        self,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
    ) -> Sequence[ExperimentRun]: ...