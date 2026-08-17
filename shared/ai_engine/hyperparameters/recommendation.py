"""Grille d'hyperparamètres pour le Recommendation Engine (filtrage collaboratif item-item).

Contrairement aux autres familles (classification/regression/clustering/
anomaly_detection), il n'existe pas d'estimateur scikit-learn pour un
recommender item-based : `build_estimators()` reflète donc cette absence
volontairement (aucun faux estimateur), et `build_parameter_spaces()` reste
la seule source de vérité pour la recherche explicite menée par
`shared.ai_engine.training.train_recommender` (jamais une fausse
`GridSearchCV` juste pour la forme).
"""

from __future__ import annotations

from typing import Any

# Aucun estimateur scikit-learn : la similarité item-item est calculée
# directement dans `train_recommender.py` (cosine_similarity), pas via un
# `Pipeline`/`BaseEstimator` classique.
_MODEL_NAME = "item_based_cf"


def build_estimators() -> dict[str, Any]:
    """Aucun estimateur sklearn pour cette famille — seul le nom du modèle est exposé."""

    return {_MODEL_NAME: None}


def build_parameter_spaces() -> dict[str, dict[str, list[Any]]]:
    """Grille explicite comparée par validation offline (Precision@K/Recall@K/HitRate@K).

    - n_neighbors : nombre d'articles similaires considérés lors du calcul du
      score de recommandation (limite le bruit des similarités faibles).
    - weighting : "implicit" (présence binaire d'une interaction) ou
      "explicit" (valeur réelle d'une note/quantité, si une colonne
      d'interaction a été résolue) — "explicit" est ignoré si aucune colonne
      d'interaction n'existe dans le dataset.
    """

    return {
        _MODEL_NAME: {
            "n_neighbors": [5, 10, 20],
            "weighting": ["implicit", "explicit"],
        }
    }
