"""Estimateurs et grilles d'hyperparamètres pour la famille Anomaly Detection.

Seule source de vérité : mêmes principes que `hyperparameters/classification.py`,
`hyperparameters/regression.py` et `hyperparameters/clustering.py`. Non supervisé,
comme le clustering : les clés ne sont PAS préfixées par ``model__`` (appliquées
directement via `estimator.set_params(**parameters)`), et il n'y a aucune
vérité terrain pour calculer une accuracy/F1 — la sélection se fait par
séparation interne des scores de décision (voir
`shared/ai_engine/evaluation/anomaly_metrics.py::rank_anomaly_candidates`).

IsolationForest est le seul candidat initial (demandé explicitement) : détection
tabulaire non supervisée, sans hypothèse de distribution, déjà éprouvée en
production ailleurs et cohérente avec l'absence de vérité terrain.
"""

from __future__ import annotations

from typing import Any, Mapping

from sklearn.base import BaseEstimator
from sklearn.ensemble import IsolationForest


def build_estimators() -> dict[str, BaseEstimator]:
    """Construit l'unique estimateur disponible pour cette famille."""

    return {
        "isolation_forest": IsolationForest(random_state=42),
    }


def build_parameter_spaces() -> dict[str, Mapping[str, Any]]:
    """Grille professionnelle pour `isolation_forest`."""

    return {
        "isolation_forest": {
            "n_estimators": [100, 200, 300],
            "max_samples": ["auto", 0.5, 0.8],
            "contamination": [0.01, 0.05, 0.1],
            "max_features": [0.5, 0.8, 1.0],
        },
    }
