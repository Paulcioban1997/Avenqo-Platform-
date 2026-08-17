"""Point d'entrée unique de la couche d'explicabilité (interne, admin uniquement).

Assemble un `ExplanationArtifact` complet à partir :
1. de l'importance native et de la permutation importance déjà calculées par
   `evaluation/sklearn_metrics.py::evaluate_model` (réutilisées telles
   quelles, jamais recalculées ici — zéro calcul dupliqué) ;
2. d'une explication SHAP additionnelle, calculée uniquement pour les
   familles de modèles nativement supportées (arbres/linéaires — voir
   `registry.py`).

Ne doit JAMAIS être appelé depuis un chemin visible par l'utilisateur final :
uniquement depuis les pipelines d'entraînement internes
(`training/train_classifier.py`, `training/train_regressor.py`,
`training/train_neural_network.py`) et de futures API admin internes.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Mapping, Sequence

import numpy as np
import pandas as pd

from shared.ai_engine.explainability.feature_importance import resolve_output_feature_names
from shared.ai_engine.explainability.shap_explainer import build_shap_explanation
from shared.ai_engine.explainability.types import ExplanationArtifact, ExplanationMethod

logger = logging.getLogger(__name__)


def explain_supervised(
    pipeline: Any,
    features: pd.DataFrame,
    model_name: str,
    task_type: Literal["classification", "regression"],
    native_importance: Mapping[str, float],
    permutation_importance: Mapping[str, float],
    max_samples: int = 5,
) -> ExplanationArtifact:
    """Explique un `Pipeline` sklearn (ML classique) déjà entraîné et évalué.

    Best-effort : toute erreur SHAP est absorbée ici et journalisée — cette
    fonction ne lève jamais, afin de ne jamais faire échouer un entraînement
    de production pour une explication optionnelle.
    """

    method: str | None
    shap_importance: Mapping[str, float] | None
    samples: tuple[Mapping[str, float], ...]
    try:
        feature_names = resolve_output_feature_names(pipeline)
        method, shap_importance, samples = build_shap_explanation(
            pipeline, features, feature_names, task_type, max_samples
        )
    except Exception:
        logger.warning(
            "Échec de l'explication pour le modèle %s : repli sur la permutation importance.",
            model_name,
            exc_info=True,
        )
        method, shap_importance, samples = None, None, ()

    global_importance = shap_importance or permutation_importance or native_importance
    explanation_method = (
        ExplanationMethod.SHAP_TREE
        if method == "shap_tree"
        else ExplanationMethod.SHAP_LINEAR
        if method == "shap_linear"
        else ExplanationMethod.PERMUTATION
        if permutation_importance
        else ExplanationMethod.NATIVE
    )
    return ExplanationArtifact(
        model_name=model_name,
        task_type=task_type,
        method=explanation_method,
        global_importance=dict(global_importance),
        native_importance=dict(native_importance),
        permutation_importance=dict(permutation_importance),
        shap_importance=dict(shap_importance) if shap_importance else None,
        sample_explanations=samples,
    )


def explain_neural_network(
    model: Any,
    features: np.ndarray,
    target: np.ndarray,
    feature_names: Sequence[str],
    model_name: str,
    task_type: Literal["classification", "regression"],
    random_seed: int = 42,
) -> ExplanationArtifact:
    """Explique un réseau dense Keras déjà entraîné.

    SHAP n'est volontairement pas branché pour les réseaux de neurones : ses
    explainers dédiés (Deep/Gradient Explainer) sont fragiles avec Keras
    3/TensorFlow 2 dans cet environnement et trop coûteux pour tourner
    automatiquement après chaque entraînement. La permutation importance
    reste 100% model-agnostic et fiable — c'est la technique utilisée ici
    ("réseaux de neurones lorsque possible").
    """

    from shared.ai_engine.explainability.permutation_importance import (
        compute_neural_permutation_importance,
    )

    try:
        importance = compute_neural_permutation_importance(
            model, features, target, feature_names, task_type, random_seed
        )
    except Exception:
        logger.warning(
            "Échec de la permutation importance neuronale pour %s.",
            model_name,
            exc_info=True,
        )
        importance = {}

    return ExplanationArtifact(
        model_name=model_name,
        task_type=task_type,
        method=ExplanationMethod.PERMUTATION,
        global_importance=dict(importance),
        native_importance={},
        permutation_importance=dict(importance),
        shap_importance=None,
        sample_explanations=(),
    )
