"""Permutation importance — source unique, réutilisée par l'évaluation ET l'explicabilité.

Anciennement dupliquée en privé dans `evaluation/sklearn_metrics.py` : ce
module en est désormais l'unique implémentation pour les `Pipeline` sklearn.
Ajoute également une variante pour les réseaux de neurones Keras
(`compute_neural_permutation_importance`), qui réutilise exactement le même
algorithme `sklearn.inspection.permutation_importance` via un petit adaptateur.
"""

from typing import Any, Literal, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, RegressorMixin
from sklearn.inspection import permutation_importance as _sklearn_permutation_importance


def compute_permutation_importance(
    estimator: Any,
    features: pd.DataFrame,
    target: pd.Series,
    scoring: str,
    random_seed: int = 42,
    n_repeats: int = 5,
    max_parallel_jobs: int = 1,
) -> Mapping[str, float]:
    """Baisse de score moyenne quand chaque variable est mélangée aléatoirement."""

    result = _sklearn_permutation_importance(
        estimator,
        features,
        target,
        scoring=scoring,
        n_repeats=n_repeats,
        random_state=random_seed,
        n_jobs=max(1, max_parallel_jobs),
    )
    columns = (
        list(features.columns)
        if hasattr(features, "columns")
        else [f"feature_{index}" for index in range(np.asarray(features).shape[1])]
    )
    return {
        str(column): float(value)
        for column, value in zip(columns, result.importances_mean, strict=True)
    }


class _FittedKerasClassifier(ClassifierMixin, BaseEstimator):
    """Adapte un modèle Keras de classification déjà entraîné à l'API minimale
    (`fit`/`predict`) attendue par `sklearn.inspection.permutation_importance`,
    afin de réutiliser exactement le même algorithme que pour les `Pipeline`
    sklearn. Hérite de `ClassifierMixin`/`BaseEstimator` (requis par scikit-learn
    >= 1.6 pour exposer les tags d'estimateur, ex. `estimator_type`)."""

    def __init__(self, model: Any = None, task_type: str = "classification") -> None:
        self.model = model
        self.task_type = task_type

    def fit(self, features: np.ndarray, target: np.ndarray | None = None) -> "_FittedKerasClassifier":
        self.classes_ = np.unique(target) if target is not None else np.array([0, 1])
        self.n_features_in_ = np.asarray(features).shape[1]
        return self

    def predict(self, features: np.ndarray) -> np.ndarray:
        from shared.ai_engine.evaluation.neural_metrics import decode_neural_predictions

        raw = self.model.predict(features, verbose=0)
        return decode_neural_predictions(raw, self.task_type)


class _FittedKerasRegressor(RegressorMixin, BaseEstimator):
    """Équivalent de `_FittedKerasClassifier` pour un réseau Keras de régression."""

    def __init__(self, model: Any = None, task_type: str = "regression") -> None:
        self.model = model
        self.task_type = task_type

    def fit(self, features: np.ndarray, target: np.ndarray | None = None) -> "_FittedKerasRegressor":
        self.n_features_in_ = np.asarray(features).shape[1]
        return self

    def predict(self, features: np.ndarray) -> np.ndarray:
        from shared.ai_engine.evaluation.neural_metrics import decode_neural_predictions

        raw = self.model.predict(features, verbose=0)
        return decode_neural_predictions(raw, self.task_type)


def compute_neural_permutation_importance(
    model: Any,
    features: np.ndarray,
    target: np.ndarray,
    feature_names: Sequence[str],
    task_type: Literal["classification", "regression"],
    random_seed: int = 42,
    n_repeats: int = 5,
) -> Mapping[str, float]:
    """Permutation importance model-agnostic pour un réseau Keras déjà entraîné."""

    scoring = "accuracy" if task_type == "classification" else "r2"
    adapter_cls = _FittedKerasClassifier if task_type == "classification" else _FittedKerasRegressor
    adapter = adapter_cls(model=model, task_type=task_type).fit(features, target)
    result = _sklearn_permutation_importance(
        adapter,
        features,
        target,
        scoring=scoring,
        n_repeats=n_repeats,
        random_state=random_seed,
    )
    return {
        str(name): float(value)
        for name, value in zip(feature_names, result.importances_mean, strict=True)
    }
