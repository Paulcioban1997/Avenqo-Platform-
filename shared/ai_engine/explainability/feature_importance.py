"""Importance native des modèles (`feature_importances_`/`coef_`) — source unique.

Anciennement dupliquée en privé dans `evaluation/sklearn_metrics.py` : ce
module en est désormais l'unique implémentation, réutilisée à la fois par
l'évaluation standard (`evaluate_model`) et par l'explicabilité (`service.py`).
"""

from typing import Mapping

import numpy as np
from sklearn.pipeline import Pipeline


def resolve_output_feature_names(pipeline: Pipeline) -> list[str]:
    """Noms des variables telles que vues par le modèle (après preprocessing + sélection)."""

    preprocessor = pipeline.named_steps["preprocessor"]
    names = np.asarray(preprocessor.get_feature_names_out())
    selector = pipeline.named_steps.get("feature_selector")
    if selector is not None:
        names = names[selector.get_support()]
    return [str(name) for name in names]


def compute_native_importance(pipeline: Pipeline) -> Mapping[str, float]:
    """`feature_importances_` (arbres/boosting) ou `coef_` (modèles linéaires), sinon `{}`."""

    names = resolve_output_feature_names(pipeline)
    model = pipeline.named_steps["model"]

    if hasattr(model, "feature_importances_"):
        values = np.asarray(model.feature_importances_)
    elif hasattr(model, "coef_"):
        coefficients = np.asarray(model.coef_)
        values = (
            np.mean(np.abs(coefficients), axis=0)
            if coefficients.ndim > 1
            else np.abs(coefficients)
        )
    else:
        return {}
    return {str(name): float(value) for name, value in zip(names, values, strict=True)}
