"""Planification du ré-entraînement — port réutilisable, aucune dépendance à
une bibliothèque de tâches planifiées particulière.

Aucun scheduler externe (Celery/APScheduler/cron) n'existe dans ce dépôt
(confirmé par recherche exhaustive) : ce module reste donc volontairement
minimal — une fonction pure `is_due` (calendrier) et un mince adaptateur qui
réutilise le port `JobScheduler` déjà existant
(`shared.ai_engine.scheduler.service`) pour mettre en file une vérification.
Remplaçable plus tard par Celery Beat, un CronJob Kubernetes, Ray ou Temporal
sans changer cette couche : ces systèmes n'auraient qu'à appeler
`enqueue_retraining_check` (ou le service HTTP interne qui l'expose) sur leur
propre horloge.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.jobs.models import AIEngineJob
from shared.ai_engine.scheduler.service import JobScheduler

# Type de job utilisé pour une vérification de ré-entraînement — distinct de
# "training" (upload) pour ne jamais mélanger les deux flux dans les logs/DB.
RETRAINING_CHECK_JOB_TYPE = "retraining_check"


@dataclass(frozen=True, slots=True)
class RetrainingTarget:
    """Identifie une tâche IA à évaluer périodiquement pour un ré-entraînement."""

    tenant: TenantContext
    module_code: str
    task_code: str


def is_due(last_run_at: datetime | None, interval_days: int, now: datetime) -> bool:
    """Vrai si `interval_days` se sont écoulés depuis `last_run_at` (ou jamais exécuté)."""

    if last_run_at is None:
        return True
    return (now - last_run_at) >= timedelta(days=interval_days)


def enqueue_retraining_check(scheduler: JobScheduler, target: RetrainingTarget) -> str:
    """Met en file une vérification de ré-entraînement via le port `JobScheduler` existant."""

    job = AIEngineJob(
        tenant=target.tenant,
        module_code=target.module_code,
        task_code=target.task_code,
        job_type=RETRAINING_CHECK_JOB_TYPE,
    )
    return scheduler.enqueue(job)
