"""Métriques adaptées aux modèles de regroupement non supervisé.

Autorité unique d'évaluation des modèles de clustering (KMeans, MiniBatchKMeans,
DBSCAN, OPTICS, Agglomerative, Birch, Gaussian Mixture, Spectral Clustering),
utilisée par le pipeline officiel de `shared.ai_engine.training`.
"""

from typing import Mapping, Sequence

import numpy as np
from sklearn.metrics import (
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)


def evaluate_clusters(
    features: np.ndarray,
    labels: np.ndarray,
) -> Mapping[str, float]:
    """Calcule la qualité des groupes et le taux de bruit DBSCAN/OPTICS.

    DBSCAN/OPTICS attribuent le label ``-1`` aux observations considérées
    comme du bruit. Ces observations sont retirées des métriques de
    séparation, mais leur proportion reste enregistrée dans ``noise_ratio``.
    """

    labels = np.asarray(labels)
    usable = labels != -1
    clean_features = np.asarray(features)[usable]
    clean_labels = labels[usable]
    cluster_count = len(set(clean_labels.tolist()))
    metrics = {
        "cluster_count": float(cluster_count),
        "noise_ratio": float(np.mean(~usable)),
    }
    if cluster_count < 2 or len(clean_features) <= cluster_count:
        metrics.update(
            silhouette=-1.0,
            davies_bouldin=float("inf"),
            calinski_harabasz=0.0,
        )
        return metrics

    metrics.update(
        silhouette=float(silhouette_score(clean_features, clean_labels)),
        davies_bouldin=float(
            davies_bouldin_score(clean_features, clean_labels)
        ),
        calinski_harabasz=float(
            calinski_harabasz_score(clean_features, clean_labels)
        ),
    )
    return metrics


def rank_clustering_candidates(
    candidates: Sequence[Mapping[str, float]],
) -> list[float]:
    """Classe des candidats (familles et hyperparamètres confondus).

    Combine les trois métriques professionnelles standard — Silhouette (plus
    haut = mieux), Davies-Bouldin (plus bas = mieux) et Calinski-Harabasz
    (plus haut = mieux) — après normalisation min-max sur l'ensemble des
    candidats réellement comparables, puis pénalise le taux de bruit. Un seul
    score composite par candidat est retourné (même ordre que `candidates`),
    ce qui permet à l'AI Engine de choisir seul le meilleur modèle sans
    jamais exposer un nom d'algorithme ni une métrique technique à
    l'utilisateur final.
    """

    comparable = [index for index, metrics in enumerate(candidates) if metrics["cluster_count"] >= 2]
    scores = [-1.0 - metrics["noise_ratio"] for metrics in candidates]
    if not comparable:
        return scores

    def normalize(values: list[float], invert: bool = False) -> list[float]:
        lowest, highest = min(values), max(values)
        if highest == lowest:
            return [0.5] * len(values)
        normalized = [(value - lowest) / (highest - lowest) for value in values]
        return [1.0 - value for value in normalized] if invert else normalized

    silhouettes = normalize([candidates[index]["silhouette"] for index in comparable])
    davies_bouldin = normalize(
        [candidates[index]["davies_bouldin"] for index in comparable], invert=True
    )
    calinski_harabasz = normalize(
        [candidates[index]["calinski_harabasz"] for index in comparable]
    )
    for position, index in enumerate(comparable):
        composite = (silhouettes[position] + davies_bouldin[position] + calinski_harabasz[position]) / 3
        scores[index] = composite - candidates[index]["noise_ratio"]
    return scores

