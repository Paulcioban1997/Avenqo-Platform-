"""Entraînement réel du Recommendation Engine (filtrage collaboratif item-item).

Approche volontairement simple pour une V1 lisible par un développeur junior :
similarité cosine entre articles, calculée à partir d'une matrice
client x article construite depuis les interactions réellement présentes
dans le dataset (jamais de colonne ou de ligne inventée). Plusieurs
configurations (`n_neighbors`, `weighting`) sont comparées par validation
offline (Precision@K/Recall@K/HitRate@K, jamais exposées à l'utilisateur
final) — une seule est conservée, exactement comme les autres familles
(classification/regression/clustering/anomaly_detection/forecasting)
choisissent un seul modèle gagnant.

Cette architecture reste volontairement un "adaptateur" simple : remplacer
`_fit_recommender`/`_score_items` par du matrix factorization, des
embeddings ou un recommender hybride plus tard ne demande de toucher qu'à ce
fichier et à `recommender.py`, jamais au reste du pipeline (Model Registry,
PredictionRuntime, TrainingDispatcher).
"""

from __future__ import annotations

from itertools import product
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

import joblib
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.training.experiment_logger import ExperimentLogger
from shared.ai_engine.training.recommendation_result import RecommendationTrainingResult
from shared.ai_engine.training.recommender import ItemBasedRecommender
from shared.ai_engine.training.run_context import TrainingRunContext


class InsufficientInteractionsError(ValueError):
    """Trop peu d'interactions client/article exploitables pour entraîner un recommender."""


def train_recommender(
    data: pd.DataFrame,
    user_column: str,
    item_column: str,
    interaction_column: str | None,
    dataset: DatasetArtifact,
    version: str,
    run_context: TrainingRunContext,
    parameter_spaces: Mapping[str, Mapping[str, Any]],
    destination: Path,
    experiment_logger: ExperimentLogger,
    minimum_interactions: int = 20,
    top_k: int = 5,
) -> RecommendationTrainingResult:
    """Prépare les interactions, cherche la meilleure configuration, sauvegarde et journalise."""

    run = experiment_logger.start(dataset, version, run_context)
    started = perf_counter()
    try:
        interactions = _clean_interactions(data, user_column, item_column, interaction_column)
        if len(interactions) < minimum_interactions:
            raise InsufficientInteractionsError(
                f"Only {len(interactions)} usable interactions found, "
                f"{minimum_interactions} required to train a recommender."
            )

        candidate_grid = parameter_spaces.get("item_based_cf", {})
        n_neighbors_options = candidate_grid.get("n_neighbors", [10])
        weighting_options = candidate_grid.get("weighting", ["implicit"])
        if interaction_column is None:
            # Aucune colonne d'interaction résolue : "explicit" n'a pas de
            # sens (rien à pondérer), jamais de valeur inventée.
            weighting_options = ["implicit"]

        best_parameters, best_metrics = _search_best_configuration(
            interactions, n_neighbors_options, weighting_options, top_k
        )

        recommender = _fit_recommender(
            interactions, best_parameters["weighting"], best_parameters["n_neighbors"]
        )
        model_path = _save_recommender(recommender, destination)

        experiment_logger.complete(
            run,
            run_context,
            model_name="item_based_collaborative_filtering",
            parameter_space=candidate_grid,
            best_parameters=best_parameters,
            metrics=best_metrics,
            model_path=model_path,
            preprocessor_path=None,
            duration_seconds=perf_counter() - started,
        )
        return RecommendationTrainingResult(
            model_name="item_based_collaborative_filtering",
            recommender=recommender,
            best_parameters=best_parameters,
            metrics=best_metrics,
            model_path=model_path,
        )
    except Exception:
        experiment_logger.fail(run, perf_counter() - started)
        raise


def _clean_interactions(
    data: pd.DataFrame,
    user_column: str,
    item_column: str,
    interaction_column: str | None,
) -> pd.DataFrame:
    """Garde uniquement les lignes exploitables (client ET article présents)."""

    columns = [user_column, item_column] + ([interaction_column] if interaction_column else [])
    interactions = data[columns].dropna(subset=[user_column, item_column]).copy()
    interactions[user_column] = interactions[user_column].astype(str)
    interactions[item_column] = interactions[item_column].astype(str)
    return interactions.reset_index(drop=True)


def _fit_recommender(interactions: pd.DataFrame, weighting: str, n_neighbors: int) -> ItemBasedRecommender:
    """Construit la matrice client x article puis la similarité cosine article x article."""

    user_column, item_column = interactions.columns[0], interactions.columns[1]
    interaction_column = interactions.columns[2] if weighting == "explicit" and len(interactions.columns) > 2 else None

    if interaction_column is not None:
        matrix = interactions.pivot_table(
            index=user_column, columns=item_column, values=interaction_column, aggfunc="mean", fill_value=0.0
        )
    else:
        matrix = interactions.assign(_present=1.0).pivot_table(
            index=user_column, columns=item_column, values="_present", aggfunc="max", fill_value=0.0
        )

    similarity = cosine_similarity(matrix.T.to_numpy())
    item_similarity = pd.DataFrame(similarity, index=matrix.columns, columns=matrix.columns)

    user_history = {
        str(user): set(items[items > 0].index)
        for user, items in matrix.iterrows()
    }
    item_popularity = tuple((matrix > 0).sum(axis=0).sort_values(ascending=False).index)

    return ItemBasedRecommender(
        item_similarity=item_similarity,
        user_history=user_history,
        item_popularity=item_popularity,
        n_neighbors=min(n_neighbors, max(len(item_popularity) - 1, 1)),
    )


def _search_best_configuration(
    interactions: pd.DataFrame,
    n_neighbors_options: list[int],
    weighting_options: list[str],
    top_k: int,
) -> tuple[dict[str, Any], dict[str, float]]:
    """Compare chaque configuration par validation offline, garde la meilleure HitRate@K."""

    best_parameters: dict[str, Any] | None = None
    best_metrics: dict[str, float] | None = None
    for n_neighbors, weighting in product(n_neighbors_options, weighting_options):
        metrics = _evaluate_configuration(interactions, weighting, n_neighbors, top_k)
        if best_metrics is None or metrics["hit_rate_at_k"] > best_metrics["hit_rate_at_k"]:
            best_metrics = metrics
            best_parameters = {"n_neighbors": n_neighbors, "weighting": weighting}

    assert best_parameters is not None and best_metrics is not None
    return best_parameters, best_metrics


def _evaluate_configuration(
    interactions: pd.DataFrame, weighting: str, n_neighbors: int, top_k: int
) -> dict[str, float]:
    """Validation offline "leave-last-interaction-out" : cache une interaction par
    client (ceux qui en ont au moins deux), ré-entraîne sans elle, vérifie si
    l'article caché apparaît dans les recommandations."""

    user_column, item_column = interactions.columns[0], interactions.columns[1]
    counts = interactions.groupby(user_column).size()
    evaluable_users = counts[counts >= 2].index
    if len(evaluable_users) == 0:
        return {"hit_rate_at_k": 0.0, "precision_at_k": 0.0, "recall_at_k": 0.0}

    held_out_rows = interactions.groupby(user_column).tail(1)
    held_out = {
        str(row[user_column]): str(row[item_column])
        for _, row in held_out_rows.iterrows()
        if row[user_column] in evaluable_users
    }
    train_interactions = interactions.drop(held_out_rows[held_out_rows[user_column].isin(evaluable_users)].index)

    recommender = _fit_recommender(train_interactions, weighting, n_neighbors)

    hits = 0
    for user_id, hidden_item in held_out.items():
        recommended = recommender.recommend(user_id, top_k)
        if hidden_item in recommended:
            hits += 1

    users_evaluated = len(held_out)
    return {
        "hit_rate_at_k": hits / users_evaluated,
        "precision_at_k": hits / (users_evaluated * top_k),
        "recall_at_k": hits / users_evaluated,
    }


def _save_recommender(recommender: ItemBasedRecommender, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    model_path = destination / "model.joblib"
    joblib.dump(recommender, model_path)
    return model_path
