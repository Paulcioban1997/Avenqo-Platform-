"""Implémentations FastAPI du port `JobScheduler` de l'AI Engine.

L'AI Engine ne dépend jamais de FastAPI (architecture stabilisée) : ce
module vit uniquement côté backend et adapte le port
`shared.ai_engine.scheduler.service.JobScheduler` avec
`fastapi.BackgroundTasks`. Il est remplaçable plus tard par Celery, Redis,
des Kubernetes Jobs, Ray ou Temporal sans modifier l'AI Engine ni ce
Protocol : seule cette classe changerait.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from fastapi import BackgroundTasks

from shared.ai_engine.jobs.models import AIEngineJob


class FastAPIBackgroundJobScheduler:
    """Exécute les jobs IA en tâche de fond FastAPI (in-process)."""

    def __init__(
        self,
        background_tasks: BackgroundTasks,
        runner: Callable[[AIEngineJob], None],
    ) -> None:
        self._tasks = background_tasks
        self._runner = runner

    def enqueue(self, job: AIEngineJob) -> str:
        self._tasks.add_task(self._runner, job)
        return str(job.id)

    def schedule(self, job: AIEngineJob, run_at: datetime) -> str:
        # Aucune planification différée en tâche de fond in-process : le job
        # démarre immédiatement pour cette première implémentation.
        return self.enqueue(job)


class FastAPISubprocessJobScheduler:
    """Planifie seulement le lancement d'un worker isolé après la réponse HTTP.

    L'objectif n'est plus d'exécuter l'AutoML dans le process API lui-même,
    mais de démarrer rapidement un nouveau process Python dédié. Cela réduit
    le risque que `joblib`/`loky` ou un modèle gourmand en mémoire fasse
    tomber le worker HTTP qui sert aussi le frontend.
    """

    def __init__(
        self,
        background_tasks: BackgroundTasks,
        launcher: Callable[[AIEngineJob], None],
    ) -> None:
        self._tasks = background_tasks
        self._launcher = launcher

    def enqueue(self, job: AIEngineJob) -> str:
        self._tasks.add_task(self._launcher, job)
        return str(job.id)

    def schedule(self, job: AIEngineJob, run_at: datetime) -> str:
        # Même comportement : le worker isolé est lancé dès la fin de la
        # requête, sans planificateur différé supplémentaire.
        return self.enqueue(job)
