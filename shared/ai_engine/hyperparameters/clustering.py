"""Estimateurs et grilles d'hyperparamètres pour la famille Clustering.

Seule source de vérité : mêmes principes que `hyperparameters/classification.py`
et `hyperparameters/regression.py`. Contrairement aux familles supervisées, les
clés des grilles ne sont PAS préfixées par ``model__`` : `train_clusterer`
applique les paramètres directement sur l'estimateur cloné (`estimator.set_params(
**parameters)`) avant de le brancher dans le pipeline de prétraitement, il n'y a
pas de recherche via GridSearchCV/RandomizedSearchCV ici (sélection non
supervisée par Silhouette/Davies-Bouldin/Calinski-Harabasz, voir
`shared/ai_engine/evaluation/clustering_metrics.py::rank_clustering_candidates`).

Toutes les familles sont recherchées ensemble par `TrainingService.train_clustering()`
et un seul modèle gagnant est conservé — l'utilisateur ne voit jamais quel
algorithme a été choisi.
"""

from __future__ import annotations

from typing import Any, Mapping

from sklearn.base import BaseEstimator
from sklearn.cluster import (
    DBSCAN,
    OPTICS,
    AgglomerativeClustering,
    Birch,
    KMeans,
    MiniBatchKMeans,
    SpectralClustering,
)
from sklearn.mixture import GaussianMixture


def build_estimators() -> dict[str, BaseEstimator]:
    """Construit un estimateur par famille de regroupement disponible."""

    return {
        "kmeans": KMeans(random_state=42, n_init=10),
        "minibatch_kmeans": MiniBatchKMeans(random_state=42, n_init=10),
        "dbscan": DBSCAN(),
        "optics": OPTICS(),
        "agglomerative": AgglomerativeClustering(),
        "birch": Birch(),
        "gaussian_mixture": GaussianMixture(random_state=42),
        "spectral_clustering": SpectralClustering(random_state=42),
    }


def build_parameter_spaces() -> dict[str, Mapping[str, Any]]:
    """Grilles professionnelles, une entrée par modèle de `build_estimators`."""

    return {
        "kmeans": {
            "n_clusters": [2, 3, 4, 5, 6, 8, 10],
            "init": ["k-means++", "random"],
            "max_iter": [200, 300, 500],
        },
        "minibatch_kmeans": {
            "n_clusters": [2, 3, 4, 5, 6, 8, 10],
            "batch_size": [64, 128, 256],
            "max_iter": [100, 200, 300],
        },
        "dbscan": {
            "eps": [0.2, 0.3, 0.5, 0.7, 1.0, 1.5],
            "min_samples": [3, 5, 8, 10],
            "metric": ["euclidean", "manhattan"],
        },
        "optics": {
            "min_samples": [3, 5, 8, 10],
            "xi": [0.02, 0.05, 0.1],
            "min_cluster_size": [0.02, 0.05, 0.1],
        },
        "agglomerative": {
            "n_clusters": [2, 3, 4, 5, 6, 8, 10],
            "linkage": ["ward", "complete", "average", "single"],
        },
        "birch": {
            "n_clusters": [2, 3, 4, 5, 6, 8, 10],
            "threshold": [0.3, 0.5, 0.7, 1.0],
            "branching_factor": [30, 50, 70],
        },
        "gaussian_mixture": {
            "n_components": [2, 3, 4, 5, 6, 8, 10],
            "covariance_type": ["full", "tied", "diag", "spherical"],
            "init_params": ["kmeans", "k-means++", "random"],
        },
        "spectral_clustering": {
            "n_clusters": [2, 3, 4, 5, 6, 8, 10],
            "affinity": ["nearest_neighbors", "rbf"],
            "n_neighbors": [5, 10, 15],
        },
    }
