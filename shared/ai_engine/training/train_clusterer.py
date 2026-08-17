"""Entraînement réel des modèles de regroupement (clustering) sklearn.

Plusieurs familles d'algorithmes (KMeans, MiniBatchKMeans, DBSCAN, OPTICS,
Agglomerative, Birch, Gaussian Mixture, Spectral Clustering) et leurs grilles
d'hyperparamètres sont recherchées ensemble ; un seul modèle gagnant est
conservé et sauvegardé, exactement comme `train_classifier`/`train_regressor`
sélectionnent un seul modèle parmi plusieurs candidats. L'utilisateur ne voit
jamais quelle famille a gagné : la sélection est entièrement automatique,
basée sur Silhouette, Davies-Bouldin et Calinski-Harabasz.
"""

from itertools import product
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy.sparse.csgraph import connected_components
from sklearn.base import BaseEstimator, clone
from sklearn.cluster import Birch, SpectralClustering
from sklearn.neighbors import kneighbors_graph
from sklearn.pipeline import Pipeline

from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.evaluation.clustering_metrics import (
    evaluate_clusters,
    rank_clustering_candidates,
)
from shared.ai_engine.preprocessing.tabular import (
    build_clustering_pipeline,
    build_preprocessor,
    detect_feature_columns,
)
from shared.ai_engine.training.clustering_result import ClusteringTrainingResult
from shared.ai_engine.training.experiment_logger import ExperimentLogger
from shared.ai_engine.training.model_saver import save_model
from shared.ai_engine.training.run_context import TrainingRunContext


def train_clusterer(
    data: pd.DataFrame,
    dataset: DatasetArtifact,
    version: str,
    run_context: TrainingRunContext,
    estimators: Mapping[str, BaseEstimator],
    parameter_spaces: Mapping[str, Mapping[str, Any]],
    destination: Path,
    experiment_logger: ExperimentLogger,
) -> ClusteringTrainingResult:
    """Prétraite les données, cherche les paramètres et journalise le Run."""

    run = experiment_logger.start(dataset, version, run_context)
    started = perf_counter()
    try:
        columns = detect_feature_columns(data)
        preprocessor = build_preprocessor(columns)
        transformed = preprocessor.fit_transform(data)
        model_name, best_pipeline, best_parameters, labels, metrics = _search_clusters(
            data,
            transformed,
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
        return ClusteringTrainingResult(
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


def _search_clusters(
    data: pd.DataFrame,
    transformed: np.ndarray,
    preprocessor: BaseEstimator,
    estimators: Mapping[str, BaseEstimator],
    parameter_spaces: Mapping[str, Mapping[str, Any]],
) -> tuple[str, Pipeline, Mapping[str, Any], np.ndarray, Mapping[str, float]]:
    """Teste chaque famille et chaque combinaison, garde le meilleur composite."""

    candidates: list[tuple[str, Pipeline, Mapping[str, Any], np.ndarray, Mapping[str, float]]] = []
    for model_name, estimator in estimators.items():
        parameter_space = parameter_spaces.get(model_name, {})
        for parameters in _parameter_combinations(parameter_space):
            candidate = clone(estimator).set_params(**parameters)
            if not _is_feasible_candidate(candidate, transformed):
                continue
            pipeline = build_clustering_pipeline(clone(preprocessor), candidate)
            labels = np.asarray(pipeline.fit_predict(data))
            candidate_metrics = evaluate_clusters(transformed, labels)
            candidates.append((model_name, pipeline, parameters, labels, candidate_metrics))

    if not candidates:
        raise ValueError("La recherche de regroupement ne contient aucun candidat")

    scores = rank_clustering_candidates([candidate[4] for candidate in candidates])
    best_index = max(range(len(candidates)), key=lambda index: scores[index])
    model_name, pipeline, parameters, labels, metrics = candidates[best_index]
    return model_name, pipeline, parameters, labels, metrics


def _is_feasible_candidate(candidate: BaseEstimator, transformed: np.ndarray) -> bool:
    """Écarte les configurations connues comme impossibles avant leur fit.

    BIRCH ne peut produire plus de groupes finaux que de sous-groupes appris.
    SpectralClustering avec affinité k-NN exige un graphe connexe ; sinon
    sklearn poursuit avec un résultat potentiellement trompeur et avertit.
    Ces vérifications ne masquent aucun warning : elles empêchent de lancer
    des candidats mathématiquement invalides pour le dataset courant.
    """

    if isinstance(candidate, Birch) and isinstance(candidate.n_clusters, int):
        probe = clone(candidate).set_params(n_clusters=None)
        probe.fit(transformed)
        if len(probe.subcluster_centers_) < candidate.n_clusters:
            return False

    if (
        isinstance(candidate, SpectralClustering)
        and candidate.affinity == "nearest_neighbors"
    ):
        neighbors = min(candidate.n_neighbors, len(transformed) - 1)
        graph = kneighbors_graph(
            transformed,
            n_neighbors=neighbors,
            include_self=True,
        )
        if connected_components(graph, directed=False, return_labels=False) > 1:
            return False

    return True


def _parameter_combinations(
    parameter_space: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Développe une grille lisible en combinaisons de paramètres."""

    if not parameter_space:
        return ({},)
    names = tuple(parameter_space)
    values = tuple(parameter_space[name] for name in names)
    return tuple(dict(zip(names, combination, strict=True)) for combination in product(*values))
