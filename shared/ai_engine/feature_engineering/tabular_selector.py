"""Construction de la sélection de variables pour les pipelines sklearn.

Autorité unique de sélection de variables tabulaires, utilisée à la fois par
`preprocessing.tabular.build_model_pipeline` (pipeline officiel de
`shared.ai_engine.training`) et par toute stratégie de feature engineering qui
en aurait besoin.
"""

from typing import Literal

from sklearn.feature_selection import SelectKBest, f_classif, f_regression

TaskType = Literal["classification", "regression"]


def build_feature_selector(
    task_type: TaskType,
    number_of_features: int | Literal["all"] = "all",
) -> SelectKBest:
    """Retourne une sélection univariée adaptée au type de prédiction.

    La valeur ``"all"`` conserve toutes les variables. Elle permet d'avoir la
    même structure de Pipeline lorsqu'aucune réduction n'est demandée.
    """

    score_function = f_classif if task_type == "classification" else f_regression
    return SelectKBest(score_func=score_function, k=number_of_features)
