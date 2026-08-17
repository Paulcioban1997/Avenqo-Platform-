"""Cycle de vie des ExperimentRun produits par les entraînements."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.experiments import (
    ArtifactReference,
    ExperimentRepository,
    ExperimentRun,
    ExperimentStatus,
    SearchRecord,
)
from shared.ai_engine.training.run_context import TrainingRunContext


class ExperimentLogger:
    """Crée et met à jour un Run sans dépendre de sklearn ni d'une base SQL."""

    def __init__(self, repository: ExperimentRepository) -> None:
        self._repository = repository

    def start(
        self,
        dataset: DatasetArtifact,
        version: str,
        context: TrainingRunContext,
    ) -> ExperimentRun:
        run = ExperimentRun(
            tenant=dataset.tenant,
            module_code=dataset.module_code,
            task_code=dataset.task_code,
            dataset=context.dataset,
            preparation=context.preparation,
            search=SearchRecord(
                model_name="pending",
                method=context.search_method,
                parameter_space=context.parameter_spaces,
                best_parameters={},
            ),
            reproducibility=context.reproducibility,
            model_version=version,
            status=ExperimentStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        self._repository.save(run)
        return run

    def complete(
        self,
        run: ExperimentRun,
        context: TrainingRunContext,
        model_name: str,
        parameter_space: Mapping[str, Any],
        best_parameters: Mapping[str, Any],
        metrics: Mapping[str, float],
        model_path: Path,
        preprocessor_path: Path | None,
        duration_seconds: float,
        numerical_columns: tuple[str, ...] | None = None,
        categorical_columns: tuple[str, ...] | None = None,
    ) -> ExperimentRun:
        artifacts = [ArtifactReference("model", str(model_path))]
        if preprocessor_path is not None:
            artifacts.append(ArtifactReference("preprocessor", str(preprocessor_path)))
        snapshot = run.dataset
        if numerical_columns is not None and categorical_columns is not None:
            snapshot = replace(
                snapshot,
                numerical_columns=numerical_columns,
                categorical_columns=categorical_columns,
            )
        completed = replace(
            run,
            dataset=snapshot,
            status=ExperimentStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
            training_duration_seconds=duration_seconds,
            search=SearchRecord(
                model_name=model_name,
                method=context.search_method,
                parameter_space=dict(parameter_space),
                best_parameters=dict(best_parameters),
            ),
            metrics=dict(metrics),
            artifacts=tuple(artifacts),
        )
        self._repository.save(completed)
        return completed

    def fail(self, run: ExperimentRun, duration_seconds: float) -> ExperimentRun:
        failed = replace(
            run,
            status=ExperimentStatus.FAILED,
            completed_at=datetime.now(timezone.utc),
            training_duration_seconds=duration_seconds,
        )
        self._repository.save(failed)
        return failed