"""Registre des familles de modèles supportées par l'explicabilité (interne).

Associe chaque type de modèle sklearn/boosting à la technique SHAP rapide et
exacte compatible (arbre ou linéaire), ou à `"other"` quand seule la
permutation importance — garantie 100% model-agnostic — doit être utilisée.

Ajouter un nouveau modèle "boîte noire" (ex. futur AutoML) ne nécessite qu'une
entrée ici : aucune autre partie de la couche d'explicabilité n'a besoin
d'être modifiée (`shap_explainer.py` consulte uniquement ce registre).
"""

from __future__ import annotations

from typing import Any, Literal

ExplanationFamily = Literal["tree", "linear", "other"]

# Modèles nativement supportés par `shap.TreeExplainer` (calcul exact, rapide).
# NB: AdaBoost est volontairement absent — c'est un ensemble pondéré
# d'estimateurs faibles hétérogènes, pas un format d'arbres standard pour
# `shap.TreeExplainer`. Repli automatique et documenté sur la permutation
# importance (100% fiable, model-agnostic) pour AdaBoost.
_TREE_MODEL_NAMES = frozenset(
    {
        "RandomForestClassifier",
        "RandomForestRegressor",
        "ExtraTreesClassifier",
        "ExtraTreesRegressor",
        "DecisionTreeClassifier",
        "DecisionTreeRegressor",
        "GradientBoostingClassifier",
        "GradientBoostingRegressor",
        "HistGradientBoostingClassifier",
        "HistGradientBoostingRegressor",
        "XGBClassifier",
        "XGBRegressor",
        "LGBMClassifier",
        "LGBMRegressor",
        "CatBoostClassifier",
        "CatBoostRegressor",
    }
)

# Modèles nativement supportés par `shap.LinearExplainer` (calcul exact, rapide).
_LINEAR_MODEL_NAMES = frozenset(
    {
        "LogisticRegression",
        "LinearRegression",
        "Ridge",
        "Lasso",
        "ElasticNet",
    }
)


def explanation_family_for(model: Any) -> ExplanationFamily:
    """Détermine quel `shap.Explainer` rapide et exact s'applique à ce modèle."""

    name = type(model).__name__
    if name in _TREE_MODEL_NAMES:
        return "tree"
    if name in _LINEAR_MODEL_NAMES:
        return "linear"
    return "other"


def is_shap_supported(model: Any) -> bool:
    """`True` si `model` appartient à une famille nativement gérée par SHAP."""

    return explanation_family_for(model) != "other"
