"""Entraînement réel des modèles de détection d'anomalies (IsolationForest).

Même architecture que `train_clusterer.py` : non supervisé, pas de colonne
cible, pas de `train_test_split` (le modèle est ajusté sur l'ensemble des
données, comme le clustering). Une seule famille candidate (IsolationForest,
voir `shared/ai_engine/hyperparameters/anomaly.py`) est recherchée sur sa
grille d'hyperparamètres ; un seul modèle gagnant est conservé, classé par
séparation interne des scores de décision — jamais par une accuracy
fabriquée artificiellement (voir
`shared/ai_engine/evaluation/anomaly_metrics.py`).
"""

from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, clone
from sklearn.model_selection import ParameterGrid
from sklearn.pipeline import Pipeline

from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.evaluation.anomaly_metrics import (
    evaluate_anomalies,
    rank_anomaly_candidates,
)
from shared.ai_engine.preprocessing.tabular import (
    build_clustering_pipeline,
    build_preprocessor,
    detect_feature_columns,
)
from shared.ai_engine.training.anomaly_result import AnomalyTrainingResult
from shared.ai_engine.training.experiment_logger import ExperimentLogger
from shared.ai_engine.training.model_saver import save_model
from shared.ai_engine.training.run_context import TrainingRunContext


def train_anomaly_detector(
    data: pd.DataFrame,
    dataset: DatasetArtifact,
    version: str,
    run_context: TrainingRunContext,
    estimators: Mapping[str, BaseEstimator],
    parameter_spaces: Mapping[str, Mapping[str, Any]],
    destination: Path,
    experiment_logger: ExperimentLogger,
) -> AnomalyTrainingResult:
    """Prétraite les données, cherche les paramètres et journalise le Run."""

    run = experiment_logger.start(dataset, version, run_context)
    started = perf_counter()
    try:
        columns = detect_feature_columns(data)
        preprocessor = build_preprocessor(columns)
        model_name, best_pipeline, best_parameters, labels, metrics = _search_anomalies(
            data,
            preprocessor,
            estimators,
            parameter_spaces,
        )
        paths = save_model(best_pipeline, destination)
        experiment_logger.complete(
            run,
            run_context,
            model_name,
            parameter_spaces.get(model_name, {}),
            best_parameters,
            metrics,
            paths.model,
            paths.preprocessor,
            perf_counter() - started,
            columns.numerical,
            columns.categorical,
        )
        return AnomalyTrainingResult(
            model_name=model_name,
            pipeline=best_pipeline,
            best_parameters=best_parameters,
            metrics=metrics,
            labels=labels,
            numerical_columns=columns.numerical,
            categorical_columns=columns.categorical,
            model_path=paths.model,
            preprocessor_path=paths.preprocessor,
        )
    except Exception:
        experiment_logger.fail(run, perf_counter() - started)
        raise


def _search_anomalies(
    data: pd.DataFrame,
    preprocessor: BaseEstimator,
    estimators: Mapping[str, BaseEstimator],
    parameter_spaces: Mapping[str, Mapping[str, Any]],
) -> tuple[str, Pipeline, Mapping[str, Any], np.ndarray, Mapping[str, float]]:
    """Teste chaque combinaison IsolationForest, garde la meilleure séparation."""

    candidates: list[tuple[str, Pipeline, Mapping[str, Any], np.ndarray, Mapping[str, float]]] = []
    for model_name, estimator in estimators.items():
        parameter_space = dict(parameter_spaces.get(model_name, {}))
        combinations = list(ParameterGrid(parameter_space)) if parameter_space else [{}]
        for parameters in combinations:
            candidate = clone(estimator).set_params(**parameters)
            pipeline = build_clustering_pipeline(clone(preprocessor), candidate)
            pipeline.fit(data)
            labels = np.asarray(pipeline.predict(data))
            transformed = pipeline.named_steps["preprocessor"].transform(data)
            scores = np.asarray(pipeline.named_steps["model"].decision_function(transformed))
            candidate_metrics = evaluate_anomalies(scores, labels)
            candidates.append((model_name, pipeline, parameters, labels, candidate_metrics))

    if not candidates:
        raise ValueError("La recherche de détection d'anomalies ne contient aucun candidat")

    scores = rank_anomaly_candidates([candidate[4] for candidate in candidates])
    best_index = max(range(len(candidates)), key=lambda index: scores[index])
    return candidates[best_index]
