"""Déclenche et exécute automatiquement l'entraînement après un import réussi.

Aucun bouton "Train Model" n'existe : `dispatch()` est appelé immédiatement
après un import de dataset réussi et planifie tout le pipeline (schema déjà
détecté à l'import, résolution automatique de la cible, nettoyage implicite
via le preprocessing sklearn, recherche d'hyperparamètres GridSearchCV,
entraînement, évaluation, sélection, Model Registry, activation) en tâche de
fond. L'utilisateur ne voit jamais de terme technique : seuls les messages
`STAGE_*` (déjà rédigés côté métier) sont exposés via l'API de statut.
"""

from __future__ import annotations

import csv
import logging
import platform
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import UUID

import pandas as pd
import sklearn
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import (
    AIJob,
    Dataset,
    DatasetProfile,
    JobStatus,
    Module,
    ModelRegistry as DBModelRegistry,
    TrainingJob,
)
from backend.app.services.dataset_import_service import DatasetImportService
from backend.app.services.training_execution_controls import TrainingExecutionControls
from backend.app.services.target_resolution_service import (
    TargetColumnUnresolved,
    TargetResolutionService,
)
from modules.retailsense.training_specs import MODULE_TRAINING_SPECS
from shared.ai_engine.contracts import DatasetArtifact, DetectedSchema, TenantContext
from shared.ai_engine.dataset_ingestion.ml_readiness import assess_ml_readiness
from shared.ai_engine.drift.serializer import (
    load_baseline,
    load_drift_report,
    save_baseline,
    save_drift_report,
)
from shared.ai_engine.drift.service import run_drift_check
from shared.ai_engine.drift.types import DriftReport, DriftSeverity, max_severity
from shared.ai_engine.exceptions import ModelNotFoundError
from shared.ai_engine.experiments import (
    DataPreparationRecord,
    DatasetSnapshot,
    ReproducibilityRecord,
    SearchMethod,
)
from shared.ai_engine.explainability.serializer import save_explanation
from shared.ai_engine.jobs.models import AIEngineJob
from shared.ai_engine.registry.registry import ModelRegistry as AIModelRegistry
from shared.ai_engine.retraining.history import (
    RetrainingHistoryEntry,
    RetrainingOutcome,
    append_history_entry,
)
from shared.ai_engine.retraining.scheduler import is_due
from shared.ai_engine.retraining.service import compare_models, evaluate_retraining, should_activate
from shared.ai_engine.retraining.types import (
    RetrainingDecision,
    RetrainingDecisionResult,
    RetrainingRulesConfig,
    RetrainingSignals,
)
from shared.ai_engine.scheduler.service import JobScheduler
from shared.ai_engine.task_resolution.service import TaskResolutionService
from shared.ai_engine.training.run_context import TrainingRunContext
from shared.ai_engine.training.service import TrainingService
from shared.ai_engine.versioning.service import record_version
from shared.ai_engine.versioning.service import rollback as rollback_version
from shared.ai_engine.versioning.types import RollbackResult

logger = logging.getLogger(__name__)

# Messages business-friendly approuvés — jamais de nom de modèle, d'algorithme
# ni de métrique technique dans cette liste.
STAGE_PREPARING = "Preparing your AI workspace..."
STAGE_ANALYZING = "Analyzing your business data..."
STAGE_BUILDING = "Building intelligent models..."
STAGE_OPTIMIZING = "Optimizing AI..."
STAGE_FINALIZING = "Finalizing your workspace..."
STAGE_READY = "Your AI workspace is ready."

# Job types distincts — jamais mélangés dans les logs/DB (upload vs. Auto
# Retraining Enterprise, Phase 8).
JOB_TYPE_TRAINING = "training"
JOB_TYPE_RETRAINING = "retraining"

_RETRAINING_CONFIG = RetrainingRulesConfig()



class TrainingDispatcher:
    """Crée un job d'entraînement puis l'exécute automatiquement en tâche de fond."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        training_service: TrainingService,
        ai_model_registry: AIModelRegistry,
        target_resolver: TargetResolutionService,
        execution_controls: TrainingExecutionControls,
        scheduler: JobScheduler | None = None,
        task_resolver: TaskResolutionService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._training = training_service
        self._registry = ai_model_registry
        self._resolver = target_resolver
        self._execution_controls = execution_controls
        self._scheduler = scheduler
        # Phase 18.2 : détecte, à partir des données réellement importées,
        # quelles capacités IA génériques sont possibles (voir
        # `shared/ai_engine/task_resolution`) — seule source utilisée pour
        # décider quelles tâches automatiques déclencher, en plus de ce que
        # le module autorise (`MODULE_TRAINING_SPECS`).
        self._task_resolver = task_resolver or TaskResolutionService()

    def attach_scheduler(self, scheduler: JobScheduler) -> None:
        self._scheduler = scheduler

    def invalidate_dataset_models(
        self,
        tenant: TenantContext,
        dataset_id: UUID,
    ) -> None:
        invalidate_dataset_versions(self._registry, tenant, str(dataset_id))

    def dispatch(
        self,
        tenant: TenantContext,
        dataset: Dataset,
        *,
        dataset_generation: int | None = None,
        source_connection_id: UUID | None = None,
        task_codes: set[str] | None = None,
    ) -> list[AIJob]:
        """Résout les tâches réellement exécutables puis planifie leur entraînement.

        Pipeline réel (Phase 18.2) : schéma déjà détecté à l'import ->
        `TaskResolutionService.resolve_dataset_capabilities()` sur les lignes
        du CSV importé -> intersection avec les tâches déclarées par le module
        (`resolve_tasks_for_module`) -> ne garde que celles qui ont aussi une
        configuration d'entraînement câblée (`MODULE_TRAINING_SPECS`). Un
        dataset peut rendre plusieurs tâches possibles : chacune obtient son
        propre `AIJob`/`TrainingJob` indépendant (aucune tâche n'est choisie
        arbitrairement, aucune n'est inventée si les données ne la permettent
        pas). Retourne une liste vide si ce module n'a aucune tâche
        automatique câblée, ou si aucune capacité détectée ne correspond à une
        tâche câblée : l'import de dataset existant continue de fonctionner
        normalement dans ce cas (aucune régression).
        """

        if self._scheduler is None:
            raise RuntimeError("A JobScheduler must be attached before dispatching")

        generation = dataset_generation or self._current_dataset_generation(dataset)

        module_code = dataset.profile.module_code if dataset.profile else None
        module_specs = MODULE_TRAINING_SPECS.get(module_code or "")
        if not module_specs:
            return []

        rows = self._load_dataset_rows(dataset)
        # Capacités réellement permises par les données ∩ tâches déclarées par
        # le module (catalogue) — jamais l'inverse : les training specs ne
        # décident jamais seules de ce que les données permettent.
        executable_capabilities = set(self._task_resolver.resolve_tasks_for_module(module_code, rows))
        executable_specs = {
            task_code: spec
            for task_code, spec in module_specs.items()
            if spec.capability in executable_capabilities
            and self._is_task_compatible(dataset, task_code, spec, rows)
            and (task_codes is None or task_code in task_codes)
        }
        if not executable_specs:
            return []

        session = self._session_factory()
        created: list[tuple[UUID, str]] = []
        try:
            module = session.scalar(select(Module).where(Module.code == module_code))
            if module is None:
                return []
            ai_jobs: list[AIJob] = []
            for task_code in executable_specs:
                duplicate = session.scalar(
                    select(TrainingJob.id).where(
                        TrainingJob.company_id == tenant.company_id,
                        TrainingJob.dataset_id == dataset.id,
                        TrainingJob.dataset_generation == generation,
                        TrainingJob.module_code == module_code,
                        TrainingJob.task_code == task_code,
                        TrainingJob.status.in_(
                            (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.COMPLETED)
                        ),
                    )
                )
                active = session.scalar(
                    select(TrainingJob.id).where(
                        TrainingJob.company_id == tenant.company_id,
                        TrainingJob.dataset_id == dataset.id,
                        TrainingJob.module_code == module_code,
                        TrainingJob.task_code == task_code,
                        TrainingJob.status.in_((JobStatus.PENDING, JobStatus.RUNNING)),
                    )
                )
                if duplicate is not None or active is not None:
                    continue
                ai_job = AIJob(
                    company_id=tenant.company_id,
                    module_id=module.id,
                    job_type=JOB_TYPE_TRAINING,
                    status=JobStatus.PENDING,
                    logs=STAGE_PREPARING,
                )
                training_job = TrainingJob(
                    company_id=tenant.company_id,
                    dataset_id=dataset.id,
                    dataset_generation=generation,
                    module_code=module_code,
                    task_code=task_code,
                    source_connection_id=source_connection_id,
                    algorithm="pending",
                    status=JobStatus.PENDING,
                )
                training_job.ai_job = ai_job
                try:
                    with session.begin_nested():
                        session.add_all([ai_job, training_job])
                        session.flush()
                except IntegrityError:
                    continue
                ai_jobs.append(ai_job)
                created.append((ai_job.id, task_code))
            session.commit()
        finally:
            session.close()

        for job_id, task_code in created:
            self._scheduler.enqueue(
                AIEngineJob(
                    tenant=tenant,
                    module_code=module_code,
                    task_code=task_code,
                    job_type=JOB_TYPE_TRAINING,
                    payload={"ai_job_id": str(job_id), "dataset_id": str(dataset.id)},
                )
            )
        return ai_jobs

    @staticmethod
    def _current_dataset_generation(dataset: Dataset) -> int:
        current = next((version for version in dataset.versions if version.is_current), None)
        return current.version_number if current is not None else 1

    def _is_task_compatible(
        self,
        dataset: Dataset,
        task_code: str,
        spec: Any,
        rows: list[dict[str, Any]],
    ) -> bool:
        columns = tuple(dict.fromkeys(key for row in rows for key in row))
        try:
            if spec.family in ("clustering", "anomaly_detection"):
                readiness = assess_ml_readiness(rows, family=spec.family)
                return self._log_readiness(dataset, task_code, readiness)
            if spec.family == "recommendation":
                user_column = self._resolver.resolve(columns, spec.user_column_aliases)
                item_column = self._resolver.resolve(columns, spec.item_column_aliases)
                if user_column == item_column:
                    raise TargetColumnUnresolved(
                        "Client and product columns resolved to the same column."
                    )
                readiness = assess_ml_readiness(
                    rows,
                    family=spec.family,
                    minimum_samples=getattr(spec, "minimum_interactions", None),
                )
                return self._log_readiness(dataset, task_code, readiness)

            target_column = self._resolver.resolve(columns, spec.target_aliases)
            time_column = None
            if spec.family == "forecasting":
                time_column = self._resolver.resolve(columns, spec.time_column_aliases)
            readiness = assess_ml_readiness(
                rows,
                family=spec.family,
                target_column=target_column,
                time_column=time_column,
                minimum_samples=getattr(spec, "minimum_observations", None),
            )
            return self._log_readiness(dataset, task_code, readiness)
        except TargetColumnUnresolved as exc:
            logger.info(
                "Automatic training skipped as not applicable company=%s dataset=%s task=%s reason=%s",
                dataset.company_id,
                dataset.id,
                task_code,
                str(exc),
            )
            return False

    @staticmethod
    def _log_readiness(dataset: Dataset, task_code: str, readiness) -> bool:
        if not readiness.ready:
            logger.info(
                "Automatic training skipped company=%s dataset=%s task=%s code=%s reasons=%s",
                dataset.company_id,
                dataset.id,
                task_code,
                readiness.code,
                ",".join(readiness.reasons),
            )
        return readiness.ready

    def _load_dataset_rows(self, dataset: Dataset) -> list[dict[str, Any]]:
        """Relit le CSV importé et réapplique le même typage qu'à l'import.

        Réutilise `DatasetImportService._coerce` (déjà utilisé par
        `import_csv`) pour ne jamais dupliquer la logique de typage : les
        lignes obtenues ici sont typées à l'identique de celles utilisées pour
        la détection de schéma au moment de l'upload.
        """

        content = Path(dataset.source).read_bytes()
        raw_rows = list(csv.DictReader(StringIO(content.decode("utf-8-sig"))))
        return [
            {key: DatasetImportService._coerce(value) for key, value in row.items()}
            for row in raw_rows
        ]

    def run_job(self, job: AIEngineJob) -> None:
        """Exécute réellement le pipeline complet (appelé en tâche de fond).

        Un seul callback est câblé sur le scheduler (import comme
        ré-entraînement autonome) : on aiguille simplement sur `job_type`
        pour appeler le bon pipeline, sans changer la façade DI existante.
        """

        if job.job_type == JOB_TYPE_RETRAINING:
            self.run_retraining_job(job)
            return

        ai_job_id = UUID(str(job.payload["ai_job_id"]))
        dataset_id = UUID(str(job.payload["dataset_id"]))
        session = self._session_factory()
        try:
            self._run(session, job.tenant, job.module_code, job.task_code, ai_job_id, dataset_id)
        finally:
            session.close()

    def _run(
        self,
        session: Session,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
        ai_job_id: UUID,
        dataset_id: UUID,
    ) -> None:
        ai_job = session.get(AIJob, ai_job_id)
        training_job = session.scalar(
            select(TrainingJob).where(TrainingJob.ai_job_id == ai_job_id)
        )
        dataset = session.get(Dataset, dataset_id)
        if ai_job is None or training_job is None or dataset is None:
            return

        started_at = datetime.now(timezone.utc)
        ai_job.status = JobStatus.RUNNING
        ai_job.started_at = started_at
        ai_job.logs = STAGE_ANALYZING
        training_job.status = JobStatus.RUNNING
        training_job.started_at = started_at
        session.commit()

        spec = MODULE_TRAINING_SPECS[module_code][task_code]
        previous_row = self._active_registry_row(session, tenant.company_id, module_code, task_code)
        parent_version = previous_row.version if previous_row else None
        try:
            version = started_at.strftime("%Y%m%d%H%M%S%f")
            result, model_type, run_context = self._build_and_train(
                session, tenant, module_code, task_code, spec, dataset, version, ai_job
            )

            ai_job.logs = STAGE_FINALIZING
            session.commit()

            activated, drift_report = self._finalize_and_persist(
                session,
                tenant,
                module_code,
                task_code,
                version,
                result,
                model_type,
                dataset,
                training_job,
                activation_decider=lambda candidate, *_args: bool(
                    getattr(candidate, "quality_approved", True)
                ),
            )

            self._complete(session, ai_job, training_job, result, started_at)

            # Model Versioning Enterprise (Phase 9) : chaque entraînement crée
            # automatiquement une nouvelle version tracée — aucun bouton, aucune
            # intervention utilisateur.
            self._record_version(
                tenant,
                module_code,
                task_code,
                version,
                spec.family,
                model_type,
                result,
                run_context,
                parent_version=parent_version,
                activated=activated,
                drift_report=drift_report,
                retraining_reason=None,
                triggered_rules=(),
            )
        except TargetColumnUnresolved as exc:
            logger.info(
                "Automatic training became not applicable company=%s dataset=%s module=%s task=%s reason=%s",
                tenant.company_id,
                dataset_id,
                module_code,
                task_code,
                str(exc),
            )
            self._cancel(session, ai_job, training_job, started_at)
        except Exception:
            logger.exception(
                "Automatic training failed for company=%s module=%s task=%s",
                tenant.company_id,
                module_code,
                task_code,
            )
            self._fail(session, ai_job, training_job, started_at)

    # ------------------------------------------------------------------
    # Auto Retraining Enterprise (Phase 8) — décide seule, sans bouton
    # "Train"/"Retrain", quand un ré-entraînement est nécessaire, puis le
    # déclenche en tâche de fond. Jamais exposé à l'utilisateur final : ni
    # les concepts (`RetrainingDecision`, comparaison, historique), ni un
    # quelconque terme technique.
    # ------------------------------------------------------------------

    def dispatch_retraining_check(
        self,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
        manual: bool = False,
        *,
        dataset_id: UUID | None = None,
        dataset_generation: int | None = None,
        source_connection_id: UUID | None = None,
        current_data_drift: DriftSeverity | None = None,
        precomputed_decision: RetrainingDecisionResult | None = None,
    ) -> AIJob | None:
        """Évalue les signaux et déclenche un ré-entraînement si nécessaire.

        Rapide et synchrone (aucun entraînement ici) : seule une décision
        favorable enfile un job réel en tâche de fond, pour ne jamais
        encombrer l'historique de jobs "no-op". Retourne `None` si aucun
        modèle n'est encore actif (le premier entraînement n'est pas piloté
        par cette couche) ou si le module n'a pas de tâche automatique.
        """

        if self._scheduler is None:
            raise RuntimeError("A JobScheduler must be attached before dispatching")

        spec = MODULE_TRAINING_SPECS.get(module_code, {}).get(task_code)
        if spec is None:
            return None

        try:
            self._registry.resolve_active(tenant, module_code, task_code)
        except ModelNotFoundError:
            return None

        session = self._session_factory()
        try:
            dataset = (
                session.get(Dataset, dataset_id)
                if dataset_id is not None
                else session.scalar(
                    select(Dataset)
                    .join(DatasetProfile, DatasetProfile.dataset_id == Dataset.id)
                    .where(
                        Dataset.company_id == tenant.company_id,
                        DatasetProfile.module_code == module_code,
                    )
                    .order_by(Dataset.uploaded_at.desc())
                )
            )
            if dataset is None:
                return None
            if dataset.company_id != tenant.company_id:
                return None

            previous_row = self._active_registry_row(session, tenant.company_id, module_code, task_code)
            latest_row = self._latest_registry_row(session, tenant.company_id, module_code, task_code)

            decision_result = precomputed_decision or evaluate_retraining(
                self._gather_signals(
                    tenant,
                    module_code,
                    task_code,
                    dataset,
                    previous_row,
                    latest_row,
                    manual,
                    current_data_drift=current_data_drift,
                )
            )
            triggered_rules = tuple(outcome.rule_name for outcome in decision_result.triggered_rules)

            if decision_result.decision < _RETRAINING_CONFIG.action_threshold:
                append_history_entry(
                    self._registry,
                    tenant,
                    module_code,
                    task_code,
                    RetrainingHistoryEntry(
                        decision=decision_result.decision,
                        outcome=RetrainingOutcome.NOT_NEEDED,
                        triggered_rules=triggered_rules,
                        previous_version=previous_row.version if previous_row else None,
                        previous_model_name=previous_row.model_name if previous_row else None,
                    ),
                )
                return None

            module = session.scalar(select(Module).where(Module.code == module_code))
            if module is None:
                return None

            active_job = session.scalar(
                select(TrainingJob.id).where(
                    TrainingJob.company_id == tenant.company_id,
                    TrainingJob.dataset_id == dataset.id,
                    TrainingJob.module_code == module_code,
                    TrainingJob.task_code == task_code,
                    TrainingJob.status.in_((JobStatus.PENDING, JobStatus.RUNNING)),
                )
            )
            if active_job is not None:
                return None

            ai_job = AIJob(
                company_id=tenant.company_id,
                module_id=module.id,
                job_type=JOB_TYPE_RETRAINING,
                status=JobStatus.PENDING,
                logs=STAGE_PREPARING,
            )
            training_job = TrainingJob(
                company_id=tenant.company_id,
                dataset_id=dataset.id,
                dataset_generation=dataset_generation or self._current_dataset_generation(dataset),
                module_code=module_code,
                task_code=task_code,
                source_connection_id=source_connection_id,
                algorithm="pending",
                status=JobStatus.PENDING,
            )
            training_job.ai_job = ai_job
            session.add_all([ai_job, training_job])
            session.commit()
            job_id = ai_job.id
            dataset_id = dataset.id
        finally:
            session.close()

        self._scheduler.enqueue(
            AIEngineJob(
                tenant=tenant,
                module_code=module_code,
                task_code=task_code,
                job_type=JOB_TYPE_RETRAINING,
                payload={
                    "ai_job_id": str(job_id),
                    "dataset_id": str(dataset_id),
                    "decision": int(decision_result.decision),
                    "triggered_rules": list(triggered_rules),
                },
            )
        )
        return ai_job

    def evaluate_connector_dataset(
        self,
        tenant: TenantContext,
        dataset_id: UUID,
        dataset_generation: int,
        source_connection_id: UUID,
    ) -> dict[str, Any]:
        """Run drift on one connector generation before deciding on retraining."""

        session = self._session_factory()
        try:
            dataset = session.get(Dataset, dataset_id)
            if dataset is None or dataset.company_id != tenant.company_id:
                raise ValueError("Connector evaluation dataset tenant mismatch")
            profile = session.scalar(
                select(DatasetProfile).where(DatasetProfile.dataset_id == dataset.id)
            )
            if profile is None:
                raise ValueError("Connector evaluation dataset has no profile")
            active_tasks = session.execute(
                select(DBModelRegistry.task_code, DBModelRegistry.version).where(
                    DBModelRegistry.company_id == tenant.company_id,
                    DBModelRegistry.module_code == profile.module_code,
                    DBModelRegistry.is_active.is_(True),
                )
            ).all()
            module_code = profile.module_code
            dataset_source = dataset.source
            if not active_tasks:
                jobs = self.dispatch(
                    tenant,
                    dataset,
                    dataset_generation=dataset_generation,
                    source_connection_id=source_connection_id,
                )
                return {
                    "decision": "initial_training",
                    "reason": "no_active_model",
                    "drift": {},
                    "ai_job_ids": [str(job.id) for job in jobs],
                }
        finally:
            session.close()

        current_data = pd.read_csv(dataset_source)
        drift_metrics: dict[str, Any] = {}
        ai_job_ids: list[str] = []
        plans: list[tuple[str, DriftSeverity, RetrainingDecisionResult]] = []
        session = self._session_factory()
        try:
            stable_dataset = session.get(Dataset, dataset_id)
            if stable_dataset is None or stable_dataset.company_id != tenant.company_id:
                raise ValueError("Connector evaluation dataset tenant mismatch")
            for task_code, version in active_tasks:
                try:
                    baseline = load_baseline(
                        self._registry,
                        tenant,
                        module_code,
                        task_code,
                        version,
                    )
                    current_features = current_data.reindex(columns=baseline.features.columns)
                    report = run_drift_check(baseline, current_features)
                    severity = max_severity(
                        report.data_drift.overall_severity,
                        report.prediction_drift.severity
                        if report.prediction_drift is not None
                        else DriftSeverity.NONE,
                    )
                    drift_metrics[task_code] = {
                        "severity": severity.name.lower(),
                        "drifted_feature_ratio": report.data_drift.drifted_feature_ratio,
                        "generated_at": report.generated_at,
                    }
                except (FileNotFoundError, OSError, ValueError):
                    logger.warning(
                        "Connector baseline unavailable company=%s source=%s task=%s",
                        tenant.company_id,
                        source_connection_id,
                        task_code,
                    )
                    severity = DriftSeverity.NONE
                    drift_metrics[task_code] = {"severity": "unavailable"}

                previous_row = self._active_registry_row(
                    session, tenant.company_id, module_code, task_code
                )
                latest_row = self._latest_registry_row(
                    session, tenant.company_id, module_code, task_code
                )
                signals = self._gather_signals(
                    tenant,
                    module_code,
                    task_code,
                    stable_dataset,
                    previous_row,
                    latest_row,
                    False,
                    current_data_drift=severity,
                )
                plans.append((task_code, severity, evaluate_retraining(signals)))
        finally:
            session.close()

        for task_code, severity, decision_result in plans:
            job = self.dispatch_retraining_check(
                tenant,
                module_code,
                task_code,
                dataset_id=dataset_id,
                dataset_generation=dataset_generation,
                source_connection_id=source_connection_id,
                current_data_drift=severity,
                precomputed_decision=decision_result,
            )
            if job is not None:
                ai_job_ids.append(str(job.id))

        decision = max(
            (decision_result.decision for _, _, decision_result in plans),
            default=RetrainingDecision.NO_ACTION,
        )
        return {
            "decision": decision.name.lower(),
            "reason": "policy_threshold_met" if ai_job_ids else "policy_threshold_not_met",
            "drift": drift_metrics,
            "ai_job_ids": ai_job_ids,
        }

    def run_retraining_job(self, job: AIEngineJob) -> None:
        """Exécute réellement le ré-entraînement autonome (appelé en tâche de fond)."""

        ai_job_id = UUID(str(job.payload["ai_job_id"]))
        dataset_id = UUID(str(job.payload["dataset_id"]))
        decision = RetrainingDecision(int(job.payload.get("decision", RetrainingDecision.RETRAIN_REQUIRED)))
        triggered_rules = tuple(job.payload.get("triggered_rules", ()))
        session = self._session_factory()
        try:
            self._run_retraining(
                session,
                job.tenant,
                job.module_code,
                job.task_code,
                ai_job_id,
                dataset_id,
                decision,
                triggered_rules,
            )
        finally:
            session.close()

    def _run_retraining(
        self,
        session: Session,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
        ai_job_id: UUID,
        dataset_id: UUID,
        decision: RetrainingDecision,
        triggered_rules: tuple[str, ...],
    ) -> None:
        ai_job = session.get(AIJob, ai_job_id)
        training_job = session.scalar(
            select(TrainingJob).where(TrainingJob.ai_job_id == ai_job_id)
        )
        dataset = session.get(Dataset, dataset_id)
        if ai_job is None or training_job is None or dataset is None:
            return

        started_at = datetime.now(timezone.utc)
        ai_job.status = JobStatus.RUNNING
        ai_job.started_at = started_at
        ai_job.logs = STAGE_ANALYZING
        training_job.status = JobStatus.RUNNING
        training_job.started_at = started_at
        session.commit()

        spec = MODULE_TRAINING_SPECS[module_code][task_code]
        previous_row = self._active_registry_row(session, tenant.company_id, module_code, task_code)
        previous_version = previous_row.version if previous_row else None
        previous_model_name = previous_row.model_name if previous_row else None
        previous_metrics = dict(previous_row.metric) if previous_row else None

        try:
            version = started_at.strftime("%Y%m%d%H%M%S%f")
            result, model_type, run_context = self._build_and_train(
                session, tenant, module_code, task_code, spec, dataset, version, ai_job
            )

            ai_job.logs = STAGE_FINALIZING
            session.commit()

            def _decide(candidate_result: Any, drift_report: DriftReport | None, _previous_metrics: Mapping | None) -> bool:
                severity = drift_report.overall_severity if drift_report is not None else None
                comparison = compare_models(
                    spec.family, previous_metrics, dict(candidate_result.metrics), severity
                )
                return should_activate(comparison)

            activated, drift_report = self._finalize_and_persist(
                session,
                tenant,
                module_code,
                task_code,
                version,
                result,
                model_type,
                dataset,
                training_job,
                activation_decider=_decide,
            )

            self._complete(session, ai_job, training_job, result, started_at)

            # Model Versioning Enterprise (Phase 9) : chaque ré-entraînement
            # crée lui aussi automatiquement une nouvelle version tracée, avec
            # la raison réelle du déclenchement (aucune donnée inventée).
            self._record_version(
                tenant,
                module_code,
                task_code,
                version,
                spec.family,
                model_type,
                result,
                run_context,
                parent_version=previous_version,
                activated=activated,
                drift_report=drift_report,
                retraining_reason="auto_retraining",
                triggered_rules=triggered_rules,
            )

            append_history_entry(
                self._registry,
                tenant,
                module_code,
                task_code,
                RetrainingHistoryEntry(
                    decision=decision,
                    outcome=RetrainingOutcome.ACTIVATED if activated else RetrainingOutcome.KEPT_PREVIOUS,
                    triggered_rules=triggered_rules,
                    previous_version=previous_version,
                    previous_model_name=previous_model_name,
                    candidate_version=version,
                    candidate_model_name=result.model_name,
                ),
            )
        except Exception:
            logger.exception(
                "Automatic retraining failed for company=%s module=%s task=%s",
                tenant.company_id,
                module_code,
                task_code,
            )
            self._fail(session, ai_job, training_job, started_at)
            append_history_entry(
                self._registry,
                tenant,
                module_code,
                task_code,
                RetrainingHistoryEntry(
                    decision=decision,
                    outcome=RetrainingOutcome.FAILED,
                    triggered_rules=triggered_rules,
                    previous_version=previous_version,
                    previous_model_name=previous_model_name,
                ),
            )

    def _gather_signals(
        self,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
        dataset: Dataset,
        previous_row: DBModelRegistry | None,
        latest_row: DBModelRegistry | None,
        manual: bool,
        current_data_drift: DriftSeverity | None = None,
    ) -> RetrainingSignals:
        data_drift_severity = current_data_drift or DriftSeverity.NONE
        concept_drift = None
        if latest_row is not None and current_data_drift is None:
            try:
                report = load_drift_report(
                    self._registry, tenant, module_code, task_code, latest_row.version
                )
                # Le drift "distribution" (données/prédictions/cible) reste
                # indépendant du concept drift (dégradation de performance),
                # évalué séparément par la règle "performance" — pour rester
                # indépendamment configurable (voir `retraining/rules.py`).
                data_drift_severity = max_severity(
                    report.data_drift.overall_severity,
                    report.prediction_drift.severity
                    if report.prediction_drift is not None
                    else DriftSeverity.NONE,
                    report.target_drift.severity
                    if report.target_drift is not None
                    else DriftSeverity.NONE,
                )
                concept_drift = report.concept_drift
            except FileNotFoundError:
                pass
            except Exception:
                logger.warning(
                    "Could not load latest drift report for company=%s module=%s task=%s",
                    tenant.company_id,
                    module_code,
                    task_code,
                    exc_info=True,
                )

        rows_at_last_training = previous_row.dataset_rows_count if previous_row else 0
        last_trained_at = previous_row.created_at if previous_row else None
        # SQLite (utilisé en test) renvoie un datetime naïf pour
        # `server_default=func.now()` ; PostgreSQL en production renvoie déjà
        # un datetime "aware". On normalise systématiquement en UTC ici pour
        # ne jamais soustraire un datetime naïf à un datetime "aware".
        if last_trained_at is not None and last_trained_at.tzinfo is None:
            last_trained_at = last_trained_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return RetrainingSignals(
            data_drift_severity=data_drift_severity,
            concept_drift=concept_drift,
            rows_at_last_training=rows_at_last_training,
            rows_current=dataset.rows_count,
            last_trained_at=last_trained_at,
            now=now,
            scheduled_due=is_due(last_trained_at, _RETRAINING_CONFIG.scheduled_interval_days, now),
            manual_trigger_requested=manual,
        )

    @staticmethod
    def _active_registry_row(
        session: Session, company_id: UUID, module_code: str, task_code: str
    ) -> DBModelRegistry | None:
        return session.scalar(
            select(DBModelRegistry).where(
                DBModelRegistry.company_id == company_id,
                DBModelRegistry.module_code == module_code,
                DBModelRegistry.task_code == task_code,
                DBModelRegistry.is_active.is_(True),
            )
        )

    @staticmethod
    def _latest_registry_row(
        session: Session, company_id: UUID, module_code: str, task_code: str
    ) -> DBModelRegistry | None:
        return session.scalar(
            select(DBModelRegistry)
            .where(
                DBModelRegistry.company_id == company_id,
                DBModelRegistry.module_code == module_code,
                DBModelRegistry.task_code == task_code,
            )
            .order_by(DBModelRegistry.created_at.desc())
        )

    def _build_and_train(
        self,
        session: Session,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
        spec: Any,
        dataset: Dataset,
        version: str,
        ai_job: AIJob,
    ) -> tuple[Any, str, TrainingRunContext]:
        """Lit les données, résout la cible, entraîne — commun aux deux flux
        (upload et ré-entraînement autonome), zéro duplication."""

        data = pd.read_csv(dataset.source)
        # Clustering et anomaly_detection sont tous les deux non supervisés :
        # aucune colonne cible n'est résolue, aucun train_test_split n'est
        # utilisé (voir train_clusterer.py/train_anomaly.py). Recommendation
        # (Phase 22) n'a pas non plus UNE colonne cible : client/produit sont
        # résolus séparément ci-dessous, via le même TargetResolutionService.
        is_unsupervised = spec.family in ("clustering", "anomaly_detection")
        is_temporal = spec.family == "forecasting"
        is_recommendation = spec.family == "recommendation"
        target_column = (
            None
            if is_unsupervised or is_recommendation
            else self._resolver.resolve(list(data.columns), spec.target_aliases)
        )
        # Forecasting : une colonne temporelle est en plus résolue via le
        # même `TargetResolutionService` générique (alias exacts puis
        # similarité sémantique) — aucun nouveau mécanisme de résolution.
        time_column = (
            self._resolver.resolve(list(data.columns), spec.time_column_aliases)
            if is_temporal
            else None
        )

        user_column: str | None = None
        item_column: str | None = None
        interaction_column: str | None = None
        if is_recommendation:
            # Client et produit sont OBLIGATOIRES (jamais de colonne inventée) :
            # une résolution manquante ou identique pour les deux lève
            # `TargetColumnUnresolved`, capturée comme les autres tâches par
            # `run_job`/`_run` (job marqué FAILED, jamais bloquant pour les
            # autres tâches du même dataset).
            user_column = self._resolver.resolve(list(data.columns), spec.user_column_aliases)
            item_column = self._resolver.resolve(list(data.columns), spec.item_column_aliases)
            if user_column == item_column:
                raise TargetColumnUnresolved(
                    "Client and product columns resolved to the same column; "
                    "recommendation cannot be trained safely."
                )
            try:
                interaction_column = self._resolver.resolve(
                    list(data.columns), spec.interaction_column_aliases
                )
            except TargetColumnUnresolved:
                # Signal d'interaction optionnel : à défaut, les interactions
                # restent implicites (simple présence client/produit).
                interaction_column = None

        ai_job.logs = STAGE_BUILDING
        session.commit()

        # Segments d'artefacts validés en minuscules/chiffres uniquement
        # par `FileSystemModelRepository` : pas de lettres majuscules.
        artifact = DatasetArtifact(
            tenant=tenant,
            module_code=module_code,
            task_code=task_code,
            uri=dataset.source,
            schema=DetectedSchema(tables={}),
        )
        parameter_spaces = spec.build_parameter_spaces()
        row_count = len(data)
        run_context = TrainingRunContext(
            dataset=DatasetSnapshot(
                dataset_id=dataset.id,
                version=version,
                fingerprint=sha256(Path(dataset.source).read_bytes()).hexdigest(),
                uri=dataset.source,
                row_count=dataset.rows_count,
                column_count=dataset.columns_count,
            ),
            # Non supervisé (clustering/anomaly_detection) : aucune colonne
            # cible à mapper (mapping vide). Forecasting : cible ET colonne
            # temporelle mappées. Recommendation : client/produit/interaction
            # mappés (interaction absente si non résolue) — pour
            # l'auditabilité du Run dans les trois cas.
            preparation=DataPreparationRecord(
                mapping=(
                    {"user": user_column, "item": item_column, "interaction": interaction_column or ""}
                    if is_recommendation
                    else {}
                    if is_unsupervised
                    else {target_column: "target", time_column: "time"}
                    if is_temporal
                    else {target_column: "target"}
                )
            ),
            reproducibility=ReproducibilityRecord(
                random_seed=42,
                split_strategy=(
                    "expanding_window_backtest"
                    if is_temporal
                    else "leave_last_interaction_out"
                    if is_recommendation
                    else "unsupervised_full_fit"
                    if is_unsupervised
                    else "train_test_split"
                ),
                split_parameters=(
                    {"horizon": spec.horizon, "max_windows": 3}
                    if is_temporal
                    else {"top_k": spec.top_k}
                    if is_recommendation
                    else {}
                    if is_unsupervised
                    else {"test_size": 0.2}
                ),
                python_version=platform.python_version(),
                library_versions={"scikit-learn": sklearn.__version__},
                code_version="training-dispatcher-v2",
                limitations=self._resource_limitations(spec.family, row_count),
            ),
            # RandomizedSearchCV : les grilles professionnelles de
            # shared/ai_engine/hyperparameters/ sont volumineuses ; un
            # tirage aléatoire garde un temps d'entraînement raisonnable.
            # Forecasting : sélection par backtesting. Recommendation :
            # recherche explicite (grille restreinte, jamais une fausse
            # GridSearchCV) — voir `train_recommender.py`.
            search_method=(
                SearchMethod.FIXED
                if is_temporal
                else SearchMethod.GRID_SEARCH
                if is_recommendation
                else SearchMethod.RANDOMIZED_SEARCH
            ),
            parameter_spaces=parameter_spaces,
        )

        ai_job.logs = STAGE_OPTIMIZING
        session.commit()

        if spec.family == "clustering":
            result = self._training.train_clustering(
                data=data,
                dataset=artifact,
                version=version,
                run_context=run_context,
                estimators=spec.build_estimators(),
                parameter_spaces=parameter_spaces,
                max_rows=self._execution_controls.unsupervised_max_rows,
            )
            model_type = "clustering"
        elif spec.family == "recommendation":
            result = self._training.train_recommendation(
                data=data,
                user_column=user_column,
                item_column=item_column,
                interaction_column=interaction_column,
                dataset=artifact,
                version=version,
                run_context=run_context,
                parameter_spaces=parameter_spaces,
                minimum_interactions=spec.minimum_interactions,
                top_k=spec.top_k,
                search_max_rows=self._execution_controls.recommendation_search_max_rows,
                final_fit_max_rows=self._execution_controls.recommendation_final_fit_max_rows,
            )
            model_type = "recommendation"
        elif spec.family == "anomaly_detection":
            result = self._training.train_anomaly_detection(
                data=data,
                dataset=artifact,
                version=version,
                run_context=run_context,
                estimators=spec.build_estimators(),
                parameter_spaces=parameter_spaces,
                max_rows=self._execution_controls.unsupervised_max_rows,
            )
            model_type = "anomaly_detection"
        elif spec.family == "forecasting":
            result = self._training.train_forecast(
                data=data,
                target_column=target_column,
                time_column=time_column,
                dataset=artifact,
                version=version,
                run_context=run_context,
                estimators=spec.build_estimators(),
                parameter_spaces=parameter_spaces,
                candidate_families=spec.candidate_families,
                horizon=spec.horizon,
                frequency=spec.frequency,
                aggregation=spec.aggregation,
                minimum_observations=spec.minimum_observations,
                seasonal_period=spec.seasonal_period,
            )
            model_type = "forecasting"
        elif spec.family == "regression":
            result = self._training.train_regressor(
                data=data,
                target_column=target_column,
                dataset=artifact,
                version=version,
                run_context=run_context,
                estimators=spec.build_estimators(),
                parameter_spaces=parameter_spaces,
                search_max_rows=self._execution_controls.search_max_rows,
                final_fit_max_rows=self._execution_controls.final_fit_max_rows,
                permutation_max_rows=self._execution_controls.explainability_max_rows,
                explanation_max_rows=self._execution_controls.explainability_max_rows,
                max_parallel_jobs=self._execution_controls.search_max_parallel_jobs,
            )
            model_type = "regression"
        else:
            result = self._training.train_classifier(
                data=data,
                target_column=target_column,
                dataset=artifact,
                version=version,
                run_context=run_context,
                estimators=spec.build_estimators(),
                parameter_spaces=parameter_spaces,
                search_max_rows=self._execution_controls.search_max_rows,
                final_fit_max_rows=self._execution_controls.final_fit_max_rows,
                permutation_max_rows=self._execution_controls.explainability_max_rows,
                explanation_max_rows=self._execution_controls.explainability_max_rows,
                max_parallel_jobs=self._execution_controls.search_max_parallel_jobs,
            )
            model_type = "classification"

        return result, model_type, run_context

    def _resource_limitations(self, family: str, row_count: int) -> tuple[str, ...]:
        limits = [f"search_parallelism_capped_at_{self._execution_controls.search_max_parallel_jobs}"]
        if family in {"classification", "regression"}:
            if row_count > self._execution_controls.search_max_rows:
                limits.append(
                    f"search_sample_capped_at_{self._execution_controls.search_max_rows}_rows"
                )
            if row_count > self._execution_controls.final_fit_max_rows:
                limits.append(
                    f"final_fit_sample_capped_at_{self._execution_controls.final_fit_max_rows}_rows"
                )
            if row_count > self._execution_controls.explainability_max_rows:
                limits.append(
                    "explainability_sample_capped_at_"
                    f"{self._execution_controls.explainability_max_rows}_rows"
                )
        elif family in {"clustering", "anomaly_detection"}:
            if row_count > self._execution_controls.unsupervised_max_rows:
                limits.append(
                    f"unsupervised_sample_capped_at_{self._execution_controls.unsupervised_max_rows}_rows"
                )
        elif family == "recommendation":
            if row_count > self._execution_controls.recommendation_search_max_rows:
                limits.append(
                    "recommendation_search_sample_capped_at_"
                    f"{self._execution_controls.recommendation_search_max_rows}_rows"
                )
            if row_count > self._execution_controls.recommendation_final_fit_max_rows:
                limits.append(
                    "recommendation_final_fit_sample_capped_at_"
                    f"{self._execution_controls.recommendation_final_fit_max_rows}_rows"
                )
        return tuple(limits)

    def _finalize_and_persist(
        self,
        session: Session,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
        version: str,
        result: Any,
        model_type: str,
        dataset: Dataset,
        training_job: TrainingJob,
        activation_decider: Callable[[Any, "DriftReport | None", "dict | None"], bool],
    ) -> tuple[bool, DriftReport | None]:
        """Drift-check vs. modèle précédent, décision d'activation, persistance.

        Commun aux deux flux : le flux upload applique le contrôle qualité du
        résultat supervisé et le flux de ré-entraînement autonome passe la
        comparaison obligatoire (Phase 8). Les artefacts sont toujours
        enregistrés, activé ou non — versionnement immuable, audit complet.
        """

        previous_row = self._active_registry_row(session, tenant.company_id, module_code, task_code)
        previous_metrics = dict(previous_row.metric) if previous_row else None

        # Détection de drift (jamais exposée à l'utilisateur final, ne doit
        # jamais faire échouer un déploiement) : compare les nouvelles données
        # à la baseline de la version PRÉCÉDEMMENT active. Absente au premier
        # entraînement (ModelNotFoundError) et pour le clustering
        # (`result.reference_baseline` vaut alors `None`).
        new_baseline = getattr(result, "reference_baseline", None)
        drift_report: DriftReport | None = None
        if new_baseline is not None:
            try:
                previous = self._registry.resolve_active(tenant, module_code, task_code)
                previous_baseline = load_baseline(
                    self._registry, tenant, module_code, task_code, previous.version
                )
                drift_report = run_drift_check(
                    previous_baseline,
                    new_baseline.features,
                    new_baseline.predictions,
                    new_baseline.target,
                    new_baseline.metrics,
                )
                save_drift_report(self._registry, drift_report, tenant, module_code, task_code, version)
            except ModelNotFoundError:
                pass
            except Exception:
                logger.warning(
                    "Drift check failed for company=%s module=%s task=%s",
                    tenant.company_id,
                    module_code,
                    task_code,
                    exc_info=True,
                )

        activated = bool(activation_decider(result, drift_report, previous_metrics))

        if activated:
            self._registry.activate(tenant, module_code, task_code, version)

        # Explication interne (jamais exposée à l'utilisateur final) : enregistrée
        # dans le ModelRegistry existant, à côté du modèle versionné. Absente pour
        # le clustering (non concerné par la Phase 6 — `result.explanation` vaut
        # alors `None` via `getattr`, aucune régression).
        explanation = getattr(result, "explanation", None)
        if explanation is not None:
            save_explanation(self._registry, explanation, tenant, module_code, task_code, version)
        if new_baseline is not None:
            save_baseline(self._registry, new_baseline, tenant, module_code, task_code, version)

        if activated:
            self._deactivate_previous_models(session, tenant.company_id, module_code, task_code)

        session.add(
            DBModelRegistry(
                company_id=tenant.company_id,
                training_job_id=training_job.id,
                module_code=module_code,
                task_code=task_code,
                model_name=result.model_name,
                model_type=model_type,
                framework="scikit-learn",
                version=version,
                storage_path=str(result.model_path),
                metric=dict(result.metrics),
                dataset_rows_count=dataset.rows_count,
                is_active=activated,
            )
        )
        return activated, drift_report

    def _record_version(
        self,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
        version: str,
        family: str,
        model_type: str,
        result: Any,
        run_context: TrainingRunContext,
        parent_version: str | None,
        activated: bool,
        drift_report: DriftReport | None,
        retraining_reason: str | None,
        triggered_rules: tuple[str, ...],
    ) -> None:
        """Enregistre automatiquement une nouvelle version (Phase 9) après un entraînement.

        Aucun bouton, aucune intervention utilisateur : appelé après
        `_finalize_and_persist` dans les deux flux (upload et ré-entraînement
        autonome). Ne réutilise que des données déjà calculées ailleurs
        (métriques, sévérité de drift, présence d'une explication) — jamais
        de recalcul. Ne lève jamais (voir `versioning.service.record_version`) :
        un échec de traçabilité ne doit jamais faire échouer un entraînement
        qui vient pourtant de réussir.
        """

        record_version(
            self._registry,
            tenant,
            module_code,
            task_code,
            version,
            family=family,
            model_type=model_type,
            model_name=result.model_name,
            dataset=run_context.dataset,
            hyperparameters=dict(result.best_parameters),
            search_method=run_context.search_method,
            metrics=dict(result.metrics),
            baseline_metrics=getattr(result, "baseline_metrics", None),
            quality_approved=getattr(result, "quality_approved", None),
            quality_reason=getattr(result, "quality_reason", None),
            parent_version=parent_version,
            activated=activated,
            drift_report=drift_report,
            has_explanation=getattr(result, "explanation", None) is not None,
            retraining_reason=retraining_reason,
            triggered_rules=triggered_rules,
        )

    def rollback_to_version(
        self,
        tenant: TenantContext,
        module_code: str,
        task_code: str,
        target_version: str,
    ) -> RollbackResult:
        """Restaure une version passée comme active — sans réentraînement (Phase 9).

        Synchronise le pointeur `ACTIVE` de l'AI Engine (filesystem, déjà
        géré par `ModelRegistry.activate`) ET l'indicateur `is_active` en
        base (utilisé par `_active_registry_row`/l'historique/les
        comparaisons), afin que les deux ne divergent jamais après un
        rollback.
        """

        result = rollback_version(self._registry, tenant, module_code, task_code, target_version)

        session = self._session_factory()
        try:
            target_row = session.scalar(
                select(DBModelRegistry).where(
                    DBModelRegistry.company_id == tenant.company_id,
                    DBModelRegistry.module_code == module_code,
                    DBModelRegistry.task_code == task_code,
                    DBModelRegistry.version == target_version,
                )
            )
            if target_row is not None:
                self._deactivate_previous_models(session, tenant.company_id, module_code, task_code)
                target_row.is_active = True
                session.commit()
        finally:
            session.close()

        return result

    @staticmethod
    def _complete(
        session: Session,
        ai_job: AIJob,
        training_job: TrainingJob,
        result: Any,
        started_at: datetime,
    ) -> None:
        completed_at = datetime.now(timezone.utc)
        training_job.status = JobStatus.COMPLETED
        training_job.algorithm = result.model_name
        # Champs dédiés = classification uniquement (accuracy/precision/recall/f1).
        # Les métriques de régression (mae/rmse/r2) sont conservées dans
        # `ModelRegistry.metric` ci-dessus ; aucune n'est exposée à l'utilisateur.
        training_job.accuracy = result.metrics.get("accuracy")
        training_job.precision = result.metrics.get("precision")
        training_job.recall = result.metrics.get("recall")
        training_job.f1_score = result.metrics.get("f1")
        training_job.training_time = (completed_at - started_at).total_seconds()
        training_job.completed_at = completed_at

        ai_job.status = JobStatus.COMPLETED
        ai_job.completed_at = completed_at
        ai_job.duration_seconds = int((completed_at - started_at).total_seconds())
        ai_job.logs = STAGE_READY
        session.commit()

    @staticmethod
    def _deactivate_previous_models(
        session: Session, company_id: UUID, module_code: str, task_code: str
    ) -> None:
        # Phase 18.2 : scopé par (module_code, task_code) — plusieurs tâches
        # automatiques peuvent désormais tourner en parallèle pour la même
        # entreprise, chacune gardant son propre modèle actif indépendant.
        previous = session.scalars(
            select(DBModelRegistry).where(
                DBModelRegistry.company_id == company_id,
                DBModelRegistry.module_code == module_code,
                DBModelRegistry.task_code == task_code,
                DBModelRegistry.is_active.is_(True),
            )
        )
        for row in previous:
            row.is_active = False

    @staticmethod
    def _cancel(
        session: Session,
        ai_job: AIJob,
        training_job: TrainingJob,
        started_at: datetime,
    ) -> None:
        completed_at = datetime.now(timezone.utc)
        ai_job.status = JobStatus.CANCELLED
        ai_job.completed_at = completed_at
        ai_job.duration_seconds = int((completed_at - started_at).total_seconds())
        ai_job.logs = STAGE_READY
        training_job.status = JobStatus.CANCELLED
        training_job.completed_at = completed_at
        session.commit()

    @staticmethod
    def _fail(
        session: Session,
        ai_job: AIJob,
        training_job: TrainingJob,
        started_at: datetime,
    ) -> None:
        completed_at = datetime.now(timezone.utc)
        ai_job.status = JobStatus.FAILED
        ai_job.completed_at = completed_at
        ai_job.duration_seconds = int((completed_at - started_at).total_seconds())
        ai_job.logs = STAGE_PREPARING
        training_job.status = JobStatus.FAILED
        training_job.completed_at = completed_at
        session.commit()

        session.commit()
