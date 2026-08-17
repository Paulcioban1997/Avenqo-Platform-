"""Dépôt mémoire utilisé pour valider le comportement des Experiments."""

from uuid import UUID

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.experiments.models import ExperimentRun


class InMemoryExperimentRepository:
    """Stocke les Runs en mémoire avec une isolation stricte par entreprise."""

    def __init__(self) -> None:
        self._runs: dict[UUID, ExperimentRun] = {}

    def save(self, run: ExperimentRun) -> None:
        """Sauvegarde un Run sans permettre son transfert vers un autre tenant."""

        existing = self._runs.get(run.id)
        if existing is not None and existing.tenant != run.tenant:
            raise ValueError("Un Run ne peut pas changer d'entreprise")
        self._runs[run.id] = run

    def get(
        self,
        tenant: TenantContext,
        run_id: UUID,
    ) -> ExperimentRun | None:
        """Retourne le Run uniquement s'il appartient à l'entreprise demandée."""

        run = self._runs.get(run_id)
        if run is None or run.tenant != tenant:
            return None
        return run

    def list_for_task(
        self,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
    ) -> tuple[ExperimentRun, ...]:
        """Liste les Runs d'une tâche du plus récent au plus ancien."""

        selected = (
            run
            for run in self._runs.values()
            if run.tenant == tenant
            and run.module_code == module_code
            and run.task_code == task_code
        )
        return tuple(sorted(selected, key=lambda run: run.created_at, reverse=True))