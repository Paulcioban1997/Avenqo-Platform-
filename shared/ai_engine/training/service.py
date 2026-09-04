from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence

import pandas as pd
from sklearn.base import BaseEstimator

from shared.ai_engine.contracts import DatasetArtifact, TrainingCandidate
from shared.ai_engine.engine import AIEngine, AutoMLResult
from shared.ai_engine.experiments import (
    ArtifactReference,
    ExperimentRepository,
    ExperimentRun,
    ExperimentStatus,
    SearchRecord,
)
from shared.ai_engine.model_registry.repository import FileSystemModelRepository
from shared.ai_engine.training.experiment_logger import ExperimentLogger
from shared.ai_engine.training.anomaly_result import AnomalyTrainingResult
from shared.ai_engine.training.clustering_result import ClusteringTrainingResult
from shared.ai_engine.training.run_context import TrainingRunContext
from shared.ai_engine.training.forecasting_result import ForecastingTrainingResult
from shared.ai_engine.training.train_anomaly import train_anomaly_detector
from shared.ai_engine.training.train_classifier import train_classifier
from shared.ai_engine.training.train_clusterer import train_clusterer
from shared.ai_engine.training.train_forecaster import train_forecaster
from shared.ai_engine.training.train_recommender import train_recommender
from shared.ai_engine.training.train_regressor import train_regressor
from shared.ai_engine.training.training_result import SupervisedTrainingResult
from shared.ai_engine.training.deep_learning_result import DeepLearningTrainingResult
from shared.ai_engine.training.recommendation_result import RecommendationTrainingResult


class TrainingService:
    """Coordonne l'AutoML et le stockage des artefacts propres à l'entreprise."""

    def __init__(
        self,
        model_repository: FileSystemModelRepository,
        experiments: ExperimentRepository,
    ) -> None:
        self._models = model_repository
        self._experiments = experiments

    def train_classifier(
        self,
        data: pd.DataFrame,
        target_column: str,
        dataset: DatasetArtifact,
        version: str,
        run_context: TrainingRunContext,
        estimators: Mapping[str, BaseEstimator],
        parameter_spaces: Mapping[str, Mapping[str, Any]],
        test_size: float = 0.2,
        random_seed: int = 42,
        cross_validation_folds: int = 3,
        search_max_rows: int | None = None,
        final_fit_max_rows: int | None = None,
        permutation_max_rows: int | None = None,
        explanation_max_rows: int | None = None,
        max_parallel_jobs: int = 1,
    ) -> SupervisedTrainingResult:
        """Lance le pipeline sklearn partagé de classification."""

        return train_classifier(
            data,
            target_column,
            dataset,
            version,
            run_context,
            estimators,
            parameter_spaces,
            self._models.artifact_directory(
                dataset.tenant, dataset.module_code, dataset.task_code, version
            ),
            ExperimentLogger(self._experiments),
            test_size,
            random_seed,
            cross_validation_folds,
            search_max_rows,
            final_fit_max_rows,
            permutation_max_rows,
            explanation_max_rows,
            max_parallel_jobs,
        )

    def train_regressor(
        self,
        data: pd.DataFrame,
        target_column: str,
        dataset: DatasetArtifact,
        version: str,
        run_context: TrainingRunContext,
        estimators: Mapping[str, BaseEstimator],
        parameter_spaces: Mapping[str, Mapping[str, Any]],
        test_size: float = 0.2,
        random_seed: int = 42,
        cross_validation_folds: int = 3,
        search_max_rows: int | None = None,
        final_fit_max_rows: int | None = None,
        permutation_max_rows: int | None = None,
        explanation_max_rows: int | None = None,
        max_parallel_jobs: int = 1,
    ) -> SupervisedTrainingResult:
        """Lance le pipeline sklearn partagé de régression."""

        return train_regressor(
            data,
            target_column,
            dataset,
            version,
            run_context,
            estimators,
            parameter_spaces,
            self._models.artifact_directory(
                dataset.tenant, dataset.module_code, dataset.task_code, version
            ),
            ExperimentLogger(self._experiments),
            test_size,
            random_seed,
            cross_validation_folds,
            search_max_rows,
            final_fit_max_rows,
            permutation_max_rows,
            explanation_max_rows,
            max_parallel_jobs,
        )

    def train_clustering(
        self,
        data: pd.DataFrame,
        dataset: DatasetArtifact,
        version: str,
        run_context: TrainingRunContext,
        estimators: Mapping[str, BaseEstimator],
        parameter_spaces: Mapping[str, Mapping[str, Any]],
        max_rows: int | None = None,
        random_seed: int = 42,
    ) -> ClusteringTrainingResult:
        """Lance le pipeline sklearn partagé de regroupement (non supervisé).

        Recherche plusieurs familles d'algorithmes en une seule fois et ne
        conserve que le meilleur modèle (Silhouette/Davies-Bouldin/
        Calinski-Harabasz) — même principe que `train_classifier`/
        `train_regressor`, sans colonne cible.
        """

        return train_clusterer(
            data,
            dataset,
            version,
            run_context,
            estimators,
            parameter_spaces,
            self._models.artifact_directory(
                dataset.tenant, dataset.module_code, dataset.task_code, version
            ),
            ExperimentLogger(self._experiments),
            max_rows,
            random_seed,
        )

    def train_anomaly_detection(
        self,
        data: pd.DataFrame,
        dataset: DatasetArtifact,
        version: str,
        run_context: TrainingRunContext,
        estimators: Mapping[str, BaseEstimator],
        parameter_spaces: Mapping[str, Mapping[str, Any]],
        max_rows: int | None = None,
        random_seed: int = 42,
    ) -> AnomalyTrainingResult:
        """Lance le pipeline sklearn partagé de détection d'anomalies (non supervisé).

        Même principe que `train_clustering` : recherche interne sur une seule
        famille (IsolationForest), aucune vérité terrain, un seul modèle
        gagnant conservé — même architecture, aucun moteur séparé.
        """

        return train_anomaly_detector(
            data,
            dataset,
            version,
            run_context,
            estimators,
            parameter_spaces,
            self._models.artifact_directory(
                dataset.tenant, dataset.module_code, dataset.task_code, version
            ),
            ExperimentLogger(self._experiments),
            max_rows,
            random_seed,
        )

    def train_forecast(
        self,
        data: pd.DataFrame,
        target_column: str,
        time_column: str,
        dataset: DatasetArtifact,
        version: str,
        run_context: TrainingRunContext,
        estimators: Mapping[str, BaseEstimator],
        parameter_spaces: Mapping[str, Mapping[str, Any]],
        candidate_families: tuple[str, ...],
        horizon: int = 1,
        frequency: str = "auto",
        aggregation: str = "sum",
        minimum_observations: int = 12,
        seasonal_period: int = 7,
    ) -> ForecastingTrainingResult:
        """Lance le pipeline de forecasting temporel (backtesting, jamais de split aléatoire).

        Même architecture que `train_clustering`/`train_anomaly_detection` :
        recherche interne sur plusieurs candidats, un seul gagnant conservé,
        aucun moteur séparé (voir `train_forecaster.py`).
        """

        return train_forecaster(
            data,
            target_column,
            time_column,
            dataset,
            version,
            run_context,
            estimators,
            parameter_spaces,
            self._models.artifact_directory(
                dataset.tenant, dataset.module_code, dataset.task_code, version
            ),
            ExperimentLogger(self._experiments),
            candidate_families,
            horizon,
            frequency,
            aggregation,
            minimum_observations,
            seasonal_period,
        )

    def train_recommendation(
        self,
        data: pd.DataFrame,
        user_column: str,
        item_column: str,
        interaction_column: str | None,
        dataset: DatasetArtifact,
        version: str,
        run_context: TrainingRunContext,
        parameter_spaces: Mapping[str, Mapping[str, Any]],
        minimum_interactions: int = 20,
        top_k: int = 5,
        search_max_rows: int | None = None,
        final_fit_max_rows: int | None = None,
        random_seed: int = 42,
    ) -> RecommendationTrainingResult:
        """Lance le pipeline de filtrage collaboratif item-based (Phase 22).

        Même architecture que les autres familles : une recherche interne
        (ici explicite, pas de GridSearchCV — voir `train_recommender.py`)
        garde une seule configuration gagnante, aucun moteur séparé.
        """

        return train_recommender(
            data,
            user_column,
            item_column,
            interaction_column,
            dataset,
            version,
            run_context,
            parameter_spaces,
            self._models.artifact_directory(
                dataset.tenant, dataset.module_code, dataset.task_code, version
            ),
            ExperimentLogger(self._experiments),
            minimum_interactions,
            top_k,
            search_max_rows,
            final_fit_max_rows,
            random_seed,
        )

    def train_neural_regressor(
        self,
        data: pd.DataFrame,
        target_column: str,
        dataset: DatasetArtifact,
        version: str,
        run_context: TrainingRunContext,
        **options: Any,
    ) -> DeepLearningTrainingResult:
        """Entraîne un réseau neuronal Keras pour une valeur continue."""

        return self._train_neural_network(
            data, target_column, "regression", dataset, version, run_context, options
        )

    def train_neural_classifier(
        self,
        data: pd.DataFrame,
        target_column: str,
        dataset: DatasetArtifact,
        version: str,
        run_context: TrainingRunContext,
        **options: Any,
    ) -> DeepLearningTrainingResult:
        """Entraîne un réseau neuronal Keras pour prédire une classe."""

        return self._train_neural_network(
            data, target_column, "classification", dataset, version, run_context, options
        )

    def _train_neural_network(
        self,
        data: pd.DataFrame,
        target_column: str,
        task_type: str,
        dataset: DatasetArtifact,
        version: str,
        run_context: TrainingRunContext,
        options: Mapping[str, Any],
    ) -> DeepLearningTrainingResult:
        from shared.ai_engine.experiments import SearchMethod
        from shared.ai_engine.training.train_neural_network import train_neural_network

        parameters = {
            key: value
            for key, value in options.items()
            if key not in {"model_builder", "callbacks"}
        }
        context = replace(
            run_context,
            search_method=SearchMethod.FIXED,
            parameter_spaces={"dense_neural_network": parameters},
        )
        return train_neural_network(
            data=data,
            target_column=target_column,
            task_type=task_type,  # type: ignore[arg-type]
            dataset=dataset,
            version=version,
            run_context=context,
            destination=self._models.artifact_directory(
                dataset.tenant, dataset.module_code, dataset.task_code, version
            ),
            experiment_logger=ExperimentLogger(self._experiments),
            **options,
        )

    def train(
        self,
        dataset: DatasetArtifact,
        version: str,
        automl: AIEngine,
        candidates: Sequence[TrainingCandidate],
        run_context: TrainingRunContext,
    ) -> tuple[AutoMLResult, Path]:
        destination = self._models.artifact_directory(
            dataset.tenant,
            dataset.module_code,
            dataset.task_code,
            version,
        )
        run = self._start_run(dataset, version, run_context)
        started = perf_counter()

        try:
            result = automl.run(dataset, candidates)
        except Exception:
            self._fail_run(run, started)
            raise

        self._complete_run(run, result, destination, started, run_context)
        return result, destination

    def _start_run(
        self,
        dataset: DatasetArtifact,
        version: str,
        context: TrainingRunContext,
    ) -> ExperimentRun:
        started_at = datetime.now(timezone.utc)
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
            started_at=started_at,
        )
        self._experiments.save(run)
        return run

    def _complete_run(
        self,
        run: ExperimentRun,
        result: AutoMLResult,
        destination: Path,
        started: float,
        context: TrainingRunContext,
    ) -> None:
        artifacts = [ArtifactReference("model", str(destination))]
        if context.preprocessor_path is not None:
            artifacts.append(
                ArtifactReference("preprocessor", context.preprocessor_path)
            )

        completed = replace(
            run,
            status=ExperimentStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
            training_duration_seconds=perf_counter() - started,
            search=SearchRecord(
                model_name=result.candidate_id,
                method=context.search_method,
                parameter_space=context.parameter_spaces.get(
                    result.candidate_id,
                    {},
                ),
                best_parameters=dict(
                    getattr(result.model, "best_params_", {})
                ),
            ),
            metrics=dict(result.evaluation.metrics),
            artifacts=tuple(artifacts),
        )
        self._experiments.save(completed)

    def _fail_run(self, run: ExperimentRun, started: float) -> None:
        failed = replace(
            run,
            status=ExperimentStatus.FAILED,
            completed_at=datetime.now(timezone.utc),
            training_duration_seconds=perf_counter() - started,
        )
        self._experiments.save(failed)

