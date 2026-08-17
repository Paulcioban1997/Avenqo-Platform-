"""Explications SHAP — uniquement pour les familles de modèles nativement
supportées par les explainers rapides et exacts de SHAP (arbres, linéaires).

Tout le reste (SVM, k-NN, AdaBoost, réseaux de neurones...) retombe
volontairement sur la permutation importance : `shap.KernelExplainer` (le
seul mode "universel" de SHAP) est combinatoirement coûteux et trop fragile
pour tourner automatiquement après chaque entraînement en production.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Mapping, Sequence

import numpy as np

from shared.ai_engine.explainability.registry import explanation_family_for

logger = logging.getLogger(__name__)


def build_shap_explanation(
    pipeline: Any,
    features: Any,
    feature_names: Sequence[str],
    task_type: Literal["classification", "regression"],
    max_samples: int = 5,
) -> tuple[str | None, Mapping[str, float] | None, tuple[Mapping[str, float], ...]]:
    """Retourne `(méthode SHAP utilisée ou None, importance globale |SHAP| moyenne, échantillons locaux)`."""

    try:
        import shap
    except ImportError:
        logger.info("shap non installé : repli sur la permutation importance uniquement.")
        return None, None, ()

    model = pipeline.named_steps["model"]
    family = explanation_family_for(model)
    if family not in ("tree", "linear"):
        return None, None, ()

    try:
        # Toutes les étapes sauf la dernière ("model") : reproduit exactement
        # la matrice de variables que le modèle voit réellement en prédiction.
        transformed = np.asarray(pipeline[:-1].transform(features))
        explainer = (
            shap.TreeExplainer(model)
            if family == "tree"
            else shap.LinearExplainer(model, transformed)
        )
        values = np.asarray(explainer(transformed).values)

        # Classification : shape (échantillons, variables, classes).
        # Régression / linéaire binaire : shape (échantillons, variables).
        if values.ndim == 3:
            global_scores = np.abs(values).mean(axis=(0, 2))
            per_sample = np.abs(values).mean(axis=-1)
        else:
            global_scores = np.abs(values).mean(axis=0)
            per_sample = values

        global_importance = {
            str(name): float(score) for name, score in zip(feature_names, global_scores, strict=True)
        }
        sample_count = min(max_samples, per_sample.shape[0])
        samples = tuple(
            {
                str(name): float(value)
                for name, value in zip(feature_names, per_sample[index], strict=True)
            }
            for index in range(sample_count)
        )
        method = "shap_tree" if family == "tree" else "shap_linear"
        return method, global_importance, samples
    except Exception:
        logger.warning(
            "Échec du calcul SHAP pour %s : repli sur la permutation importance.",
            type(model).__name__,
            exc_info=True,
        )
        return None, None, ()
