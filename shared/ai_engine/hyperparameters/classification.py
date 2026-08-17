"""Estimateurs et grilles d'hyperparamètres pour la famille Classification.

Seule source de vérité : `TrainingDispatcher` utilise `SearchMethod.RANDOMIZED_SEARCH`
(voir `shared/ai_engine/architectures/machine_learning/optimizer.py`), donc des
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
    AdaBoostClassifier,
    ExtraTreesClassifier,
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier

logger = logging.getLogger(__name__)

try:
    from xgboost import XGBClassifier
except ImportError:  # dépendance optionnelle
    XGBClassifier = None

try:
    from lightgbm import LGBMClassifier
except ImportError:  # dépendance optionnelle
    LGBMClassifier = None

try:
    from catboost import CatBoostClassifier
except ImportError:  # dépendance optionnelle
    CatBoostClassifier = None


def build_estimators() -> dict[str, BaseEstimator]:
    """Construit un estimateur par modèle de classification disponible."""

    estimators: dict[str, BaseEstimator] = {
        "logistic_regression": LogisticRegression(max_iter=2000),
        "decision_tree": DecisionTreeClassifier(random_state=42),
        "random_forest": RandomForestClassifier(random_state=42),
        "extra_trees": ExtraTreesClassifier(random_state=42),
        "adaboost": AdaBoostClassifier(random_state=42),
        "gradient_boosting": GradientBoostingClassifier(random_state=42),
        "hist_gradient_boosting": HistGradientBoostingClassifier(random_state=42),
    }

    if XGBClassifier is not None:
        estimators["xgboost"] = XGBClassifier(random_state=42, eval_metric="logloss")
    else:
        logger.info("xgboost non installé : modèle 'xgboost' ignoré (classification).")

    if LGBMClassifier is not None:
        estimators["lightgbm"] = LGBMClassifier(random_state=42)
    else:
        logger.info("lightgbm non installé : modèle 'lightgbm' ignoré (classification).")

    if CatBoostClassifier is not None:
        estimators["catboost"] = CatBoostClassifier(random_state=42, verbose=False)
    else:
        logger.info("catboost non installé : modèle 'catboost' ignoré (classification).")

    return estimators


def build_parameter_spaces() -> dict[str, Mapping[str, Any]]:
    """Grilles professionnelles, une entrée par modèle de `build_estimators`."""

    return {
        "logistic_regression": {
            "model__C": [0.001, 0.01, 0.1, 1.0, 10.0, 100.0],
            "model__solver": ["lbfgs", "saga"],
        },
        "decision_tree": {
            "model__criterion": ["gini", "entropy", "log_loss"],
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
            "model__max_features": ["sqrt", "log2"],
            "model__bootstrap": [True, False],
        },
        "extra_trees": {
            "model__n_estimators": [100, 200, 300, 500],
            "model__max_depth": [None, 10, 20, 30, 50],
            "model__min_samples_split": [2, 5, 10, 20],
            "model__min_samples_leaf": [1, 2, 4, 8],
            "model__max_features": ["sqrt", "log2"],
            "model__bootstrap": [True, False],
        },
        "adaboost": {
            "model__n_estimators": [50, 100, 200, 300, 500],
            "model__learning_rate": [0.001, 0.01, 0.05, 0.1, 0.3, 0.5, 1.0],
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
