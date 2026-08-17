"""Recherche d'hyperparamètres Machine Learning : autorité unique GridSearchCV/RandomizedSearchCV.

`run_hyperparameter_search` est la seule implémentation de recherche
d'hyperparamètres pour les modèles ML tabulaires. Elle est utilisée
directement par le pipeline officiel de `shared.ai_engine.training`
(`train_classifier`, `train_regressor`), qui manipule des DataFrame déjà
chargés en mémoire.

`MachineLearningHyperparameterOptimizer` reste un adaptateur `NoOp` conforme
au protocole `HyperparameterOptimizer` (`optimize(candidate, dataset)`) tant
que `DatasetArtifact` ne transporte pas de données chargées : brancher une
vraie recherche à ce niveau nécessiterait un changement de contrat
(chargement de `dataset.uri`, détection de la colonne cible), ce qui
constituerait une nouvelle fonctionnalité hors du périmètre de cette
unification.
"""

from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd
from sklearn.model_selection import GridSearchCV, ParameterGrid, RandomizedSearchCV
from sklearn.pipeline import Pipeline

from shared.ai_engine.core.optimizer import NoOpHyperparameterOptimizer
from shared.ai_engine.experiments import SearchMethod


class MachineLearningHyperparameterOptimizer(NoOpHyperparameterOptimizer):
    """Adaptateur `NoOp` conforme au protocole ; la recherche réelle est `run_hyperparameter_search`."""


@dataclass(frozen=True, slots=True)
class HyperparameterSearchResult:
    """Résultat de la meilleure recherche parmi tous les modèles proposés."""

    model_name: str
    search: GridSearchCV | RandomizedSearchCV
    parameter_space: Mapping[str, Any]

    @property
    def best_pipeline(self) -> Pipeline:
        return self.search.best_estimator_

    @property
    def best_parameters(self) -> dict[str, Any]:
        """Retourne les paramètres sans le préfixe interne ``model__``."""

        return {
            key.removeprefix("model__"): value
            for key, value in self.search.best_params_.items()
        }


def run_hyperparameter_search(
    pipelines: Mapping[str, Pipeline],
    parameter_spaces: Mapping[str, Mapping[str, Any]],
    features: pd.DataFrame,
    target: pd.Series,
    method: SearchMethod,
    scoring: str,
    cross_validation_folds: int = 3,
    random_seed: int = 42,
    randomized_iterations: int = 20,
) -> HyperparameterSearchResult:
    """Entraîne chaque Pipeline et conserve celui au meilleur score CV."""

    results: list[HyperparameterSearchResult] = []
    for model_name, pipeline in pipelines.items():
        raw_space = dict(parameter_spaces.get(model_name, {}))
        sklearn_space = {
            _prefix_model_parameter(name): values for name, values in raw_space.items()
        }
        search = _build_search(
            pipeline,
            sklearn_space,
            method,
            scoring,
            cross_validation_folds,
            random_seed,
            randomized_iterations,
        )
        search.fit(features, target)
        results.append(HyperparameterSearchResult(model_name, search, raw_space))

    if not results:
        raise ValueError("Au moins un modèle doit être fourni pour l'entraînement")
    return max(results, key=lambda result: result.search.best_score_)


def _prefix_model_parameter(name: str) -> str:
    return name if "__" in name else f"model__{name}"


def _build_search(
    pipeline: Pipeline,
    parameter_space: Mapping[str, Any],
    method: SearchMethod,
    scoring: str,
    folds: int,
    random_seed: int,
    randomized_iterations: int,
) -> GridSearchCV | RandomizedSearchCV:
    common = {
        "estimator": pipeline,
        "scoring": scoring,
        "cv": folds,
        "n_jobs": -1,
        "refit": True,
        "error_score": "raise",
    }
    if method == SearchMethod.RANDOMIZED_SEARCH:
        try:
            search_iterations = min(randomized_iterations, len(ParameterGrid(parameter_space)))
        except TypeError:
            # Les distributions scipy n'ont pas une taille finie ; dans ce
            # cas RandomizedSearchCV conserve le budget demandé.
            search_iterations = randomized_iterations
        return RandomizedSearchCV(
            param_distributions=parameter_space,
            n_iter=search_iterations,
            random_state=random_seed,
            **common,
        )
    if method != SearchMethod.GRID_SEARCH:
        raise ValueError(f"Méthode sklearn non prise en charge: {method}")
    return GridSearchCV(param_grid=parameter_space, **common)

