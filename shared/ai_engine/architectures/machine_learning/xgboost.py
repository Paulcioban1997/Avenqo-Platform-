"""Candidat XGBoost, entraîné avec xgboost.XGBRegressor/XGBClassifier.

Réutilisé tel quel par la famille Forecasting (voir families/forecasting/registry.py) :
lorsque le dataset ressemble à une série temporelle univariée (une colonne date détectée
et une seule colonne numérique restante), les features sont automatiquement construites
par décalage temporel (lags) via `build_lag_features` avant l'entraînement — technique
standard pour appliquer des modèles à arbres à la prévision de séries temporelles. Sinon,
l'entraînement reste un XGBoost tabulaire générique classique (régression ou classification
selon la cardinalité de la colonne cible).

Recherche d'hyperparamètres : ZÉRO nouvelle grille ni nouvelle logique de recherche ici.
Ce fichier réutilise tel quel l'autorité unique déjà existante pour tout le Machine
Learning tabulaire — `architectures/machine_learning/optimizer.py::run_hyperparameter_search`
(GridSearchCV/RandomizedSearchCV) — ainsi que la grille "xgboost" déjà définie dans
`hyperparameters/classification.py`/`hyperparameters/regression.py` (mêmes grilles que
celles utilisées par `training/train_classifier.py`/`train_regressor.py`). Seule
différence : en mode série temporelle, la validation croisée utilise `TimeSeriesSplit`
au lieu d'un k-fold classique, pour éviter toute fuite d'information (entraîner sur le
futur pour prédire le passé).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from shared.ai_engine.architectures.machine_learning.optimizer import run_hyperparameter_search
from shared.ai_engine.contracts import DatasetArtifact
from shared.ai_engine.core.model_stub import UntrainedModel
from shared.ai_engine.core.tabular_dataset import (
    build_lag_features,
    detect_datetime_column,
    detect_target_column,
    load_dataframe,
)
from shared.ai_engine.experiments import SearchMethod
from shared.ai_engine.preprocessing.tabular import (
    build_model_pipeline,
    build_preprocessor,
    detect_feature_columns,
)

_TIME_SERIES_LAGS = 5
_RANDOMIZED_ITERATIONS = 30


class XGBoostModel(UntrainedModel):
    candidate_id = "xgboost"

    def train(self, dataset: DatasetArtifact) -> Any:
        frame = load_dataframe(dataset)
        datetime_column = detect_datetime_column(frame)
        remaining_columns = [column for column in frame.columns if column != datetime_column]

        if datetime_column is not None and len(remaining_columns) == 1:
            return self._train_time_series(frame, datetime_column, remaining_columns[0])
        exclude = (datetime_column,) if datetime_column else ()
        return self._train_tabular(frame, exclude=exclude)

    def _train_time_series(
        self, frame: pd.DataFrame, datetime_column: str, value_column: str
    ) -> Any:
        from shared.ai_engine.hyperparameters import regression as regression_hyperparameters

        ordered = frame.sort_values(datetime_column)
        series = ordered[value_column].astype("float64").reset_index(drop=True)
        features, target = build_lag_features(series, lags=_TIME_SERIES_LAGS)

        splits = min(5, max(2, len(features) // 10))
        return self._search_and_fit(
            regression_hyperparameters,
            features,
            target,
            task_type="regression",
            cross_validation=TimeSeriesSplit(n_splits=splits),
            scoring="neg_root_mean_squared_error",
        )

    def _train_tabular(self, frame: pd.DataFrame, exclude: tuple[str, ...]) -> Any:
        from shared.ai_engine.hyperparameters import classification as classification_hyperparameters
        from shared.ai_engine.hyperparameters import regression as regression_hyperparameters

        target_column = detect_target_column(frame, exclude=exclude)
        features = frame.drop(columns=[*exclude, target_column])
        target = frame[target_column]

        if pd.api.types.is_numeric_dtype(target) and target.nunique() > 20:
            folds = min(5, max(2, len(features) // 10))
            return self._search_and_fit(
                regression_hyperparameters,
                features,
                target.astype("float64"),
                task_type="regression",
                cross_validation=folds,
                scoring="neg_root_mean_squared_error",
            )

        encoded_target = pd.Series(pd.factorize(target)[0], index=target.index)
        folds = min(5, max(2, encoded_target.value_counts().min()))
        return self._search_and_fit(
            classification_hyperparameters,
            features,
            encoded_target,
            task_type="classification",
            cross_validation=folds,
            scoring="accuracy",
        )

    def _search_and_fit(
        self,
        hyperparameters_module: Any,
        features: pd.DataFrame,
        target: pd.Series,
        task_type: str,
        cross_validation: int | TimeSeriesSplit,
        scoring: str,
    ) -> Any:
        estimator = hyperparameters_module.build_estimators()["xgboost"]
        parameter_space = hyperparameters_module.build_parameter_spaces()["xgboost"]

        columns = detect_feature_columns(features)
        preprocessor = build_preprocessor(columns)
        pipeline = build_model_pipeline(preprocessor, estimator, task_type)

        result = run_hyperparameter_search(
            {"xgboost": pipeline},
            {"xgboost": parameter_space},
            features,
            target,
            method=SearchMethod.RANDOMIZED_SEARCH,
            scoring=scoring,
            cross_validation_folds=cross_validation,
            random_seed=42,
            randomized_iterations=_RANDOMIZED_ITERATIONS,
        )
        return result.best_pipeline
