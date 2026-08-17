"""Estimateurs et grilles d'hyperparamètres pour la famille Régression.

Seule source de vérité : mêmes principes que `hyperparameters/classification.py`.
`TrainingDispatcher` utilise `SearchMethod.RANDOMIZED_SEARCH` (voir
`shared/ai_engine/architectures/machine_learning/optimizer.py`), donc des
grilles volumineuses restent réalistes en temps d'entraînement (un nombre fixe
de tirages est échantillonné, indépendamment de la taille du produit cartésien).

Les dépendances optionnelles (xgboost, lightgbm, catboost) sont importées
prudemment : si l'une d'elles n'est pas installée, son modèle est simplement
absent du dictionnaire retourné — aucune erreur, aucun impact sur les autres
familles ni sur le reste du projet.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from sklearn.base import BaseEstimator
from sklearn.ensemble import (
    AdaBoostRegressor,
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.linear_model import ElasticNet, Lasso, LinearRegression, Ridge
from sklearn.tree import DecisionTreeRegressor

logger = logging.getLogger(__name__)

try:
    from xgboost import XGBRegressor
except ImportError:  # dépendance optionnelle
    XGBRegressor = None

try:
    from lightgbm import LGBMRegressor
except ImportError:  # dépendance optionnelle
    LGBMRegressor = None

try:
    from catboost import CatBoostRegressor
except ImportError:  # dépendance optionnelle
    CatBoostRegressor = None


def build_estimators() -> dict[str, BaseEstimator]:
    """Construit un estimateur par modèle de régression disponible."""

    estimators: dict[str, BaseEstimator] = {
        "linear_regression": LinearRegression(),
        "ridge": Ridge(random_state=42),
        "lasso": Lasso(random_state=42),
        "elastic_net": ElasticNet(random_state=42),
        "decision_tree": DecisionTreeRegressor(random_state=42),
        "random_forest": RandomForestRegressor(random_state=42),
        "extra_trees": ExtraTreesRegressor(random_state=42),
        "adaboost": AdaBoostRegressor(random_state=42),
        "gradient_boosting": GradientBoostingRegressor(random_state=42),
        "hist_gradient_boosting": HistGradientBoostingRegressor(random_state=42),
    }

    if XGBRegressor is not None:
        estimators["xgboost"] = XGBRegressor(random_state=42)
    else:
        logger.info("xgboost non installé : modèle 'xgboost' ignoré (régression).")

    if LGBMRegressor is not None:
        estimators["lightgbm"] = LGBMRegressor(random_state=42)
    else:
        logger.info("lightgbm non installé : modèle 'lightgbm' ignoré (régression).")

    if CatBoostRegressor is not None:
        estimators["catboost"] = CatBoostRegressor(random_state=42, verbose=False)
    else:
        logger.info("catboost non installé : modèle 'catboost' ignoré (régression).")

    return estimators


def build_parameter_spaces() -> dict[str, Mapping[str, Any]]:
    """Grilles professionnelles, une entrée par modèle de `build_estimators`."""

    return {
        "linear_regression": {
            "model__fit_intercept": [True, False],
            "model__positive": [True, False],
        },
        "ridge": {
            "model__alpha": [0.001, 0.01, 0.1, 1.0, 10.0, 100.0],
            "model__solver": ["auto", "svd", "cholesky", "lsqr", "sag"],
        },
        "lasso": {
            "model__alpha": [0.001, 0.01, 0.1, 1.0, 10.0, 100.0],
            "model__selection": ["cyclic", "random"],
        },
        "elastic_net": {
            "model__alpha": [0.001, 0.01, 0.1, 1.0, 10.0, 100.0],
            "model__l1_ratio": [0.1, 0.3, 0.5, 0.7, 0.9],
            "model__selection": ["cyclic", "random"],
        },
        "decision_tree": {
            "model__criterion": ["squared_error", "poisson", "absolute_error"],
            "model__splitter": ["best", "random"],
            "model__max_depth": [None, 10, 20, 30, 50],
            "model__min_samples_split": [2, 5, 10, 20],
            "model__min_samples_leaf": [1, 2, 4, 8],
            "model__max_features": ["sqrt", "log2", None],
        },
        "random_forest": {
            "model__n_estimators": [100, 200, 300, 500],
            "model__max_depth": [None, 10, 20, 30, 50],
            "model__min_samples_split": [2, 5, 10, 20],
            "model__min_samples_leaf": [1, 2, 4, 8],
            "model__max_features": ["sqrt", "log2", 1.0],
            "model__bootstrap": [True, False],
        },
        "extra_trees": {
            "model__n_estimators": [100, 200, 300, 500],
            "model__max_depth": [None, 10, 20, 30, 50],
            "model__min_samples_split": [2, 5, 10, 20],
            "model__min_samples_leaf": [1, 2, 4, 8],
            "model__max_features": ["sqrt", "log2", 1.0],
            "model__bootstrap": [True, False],
        },
        "adaboost": {
            "model__n_estimators": [50, 100, 200, 300, 500],
            "model__learning_rate": [0.001, 0.01, 0.05, 0.1, 0.3, 0.5, 1.0],
            "model__loss": ["linear", "square", "exponential"],
        },
        "gradient_boosting": {
            "model__n_estimators": [100, 200, 300, 500],
            "model__learning_rate": [0.01, 0.05, 0.1, 0.2],
            "model__max_depth": [3, 5, 7, 10],
            "model__subsample": [0.6, 0.8, 1.0],
            "model__min_samples_split": [2, 5, 10],
        },
        "hist_gradient_boosting": {
            "model__max_iter": [100, 200, 300, 500],
            "model__learning_rate": [0.01, 0.05, 0.1, 0.2],
            "model__max_depth": [None, 5, 10, 20],
            "model__max_leaf_nodes": [15, 31, 63, 127],
            "model__l2_regularization": [0.0, 0.1, 1.0],
        },
        "xgboost": {
            "model__n_estimators": [100, 200, 300, 500],
            "model__max_depth": [3, 5, 7, 10],
            "model__learning_rate": [0.01, 0.05, 0.1, 0.2],
            "model__subsample": [0.6, 0.8, 1.0],
            "model__colsample_bytree": [0.6, 0.8, 1.0],
            "model__gamma": [0, 0.1, 0.3, 0.5],
            "model__min_child_weight": [1, 3, 5, 7],
            "model__reg_alpha": [0, 0.1, 1],
            "model__reg_lambda": [1, 5, 10],
        },
        "lightgbm": {
            "model__n_estimators": [100, 200, 300, 500],
            "model__num_leaves": [15, 31, 63, 127],
            "model__max_depth": [-1, 5, 10, 20],
            "model__learning_rate": [0.01, 0.05, 0.1, 0.2],
            "model__subsample": [0.6, 0.8, 1.0],
            "model__colsample_bytree": [0.6, 0.8, 1.0],
            "model__reg_alpha": [0, 0.1, 1],
            "model__reg_lambda": [0, 0.1, 1],
        },
        "catboost": {
            "model__iterations": [200, 400, 600],
            "model__depth": [4, 6, 8, 10],
            "model__learning_rate": [0.01, 0.05, 0.1, 0.2],
            "model__l2_leaf_reg": [1, 3, 5, 10],
        },
    }
