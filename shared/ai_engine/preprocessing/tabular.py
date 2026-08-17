"""Détection des colonnes et construction des pipelines sklearn.

Autorité unique de preprocessing tabulaire (imputation, mise à l'échelle,
encodage), utilisée par le pipeline officiel de `shared.ai_engine.training`
(`train_classifier`, `train_regressor`, `train_clusterer`, `train_neural_network`).
"""

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd
from imblearn.pipeline import Pipeline as ImbalancedPipeline
from sklearn.base import BaseEstimator
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from shared.ai_engine.feature_engineering.tabular_selector import build_feature_selector


@dataclass(frozen=True, slots=True)
class FeatureColumns:
    """Sépare les variables utilisables selon leur type pandas."""

    numerical: tuple[str, ...]
    categorical: tuple[str, ...]


def detect_feature_columns(features: pd.DataFrame) -> FeatureColumns:
    """Détecte les nombres; toutes les autres colonnes sont catégorielles."""

    numerical = tuple(features.select_dtypes(include="number").columns)
    categorical = tuple(column for column in features if column not in numerical)
    if not numerical and not categorical:
        raise ValueError("Le jeu de données ne contient aucune variable")
    return FeatureColumns(numerical=numerical, categorical=categorical)


def build_preprocessor(columns: FeatureColumns) -> ColumnTransformer:
    """Construit les traitements numériques et catégoriels.

    Les nombres manquants sont remplacés par la médiane puis standardisés.
    Les catégories manquantes sont remplacées par la valeur la plus fréquente,
    puis encodées en colonnes binaires. Les catégories inconnues sont ignorées.
    """

    numerical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "encoder",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
            ),
        ]
    )

    transformers: list[tuple[str, Any, list[str]]] = []
    if columns.numerical:
        transformers.append(("numerical", numerical_pipeline, list(columns.numerical)))
    if columns.categorical:
        transformers.append(
            ("categorical", categorical_pipeline, list(columns.categorical))
        )
    return ColumnTransformer(transformers=transformers, remainder="drop")


def build_model_pipeline(
    preprocessor: ColumnTransformer,
    estimator: BaseEstimator,
    task_type: Literal["classification", "regression"],
    number_of_features: int | Literal["all"] = "all",
) -> Pipeline:
    """Assemble preprocessing, sélection de variables et modèle final."""

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("feature_selector", build_feature_selector(task_type, number_of_features)),
            ("model", estimator),
        ]
    )


def build_clustering_pipeline(
    preprocessor: ColumnTransformer,
    estimator: BaseEstimator,
) -> Pipeline:
    """Assemble le preprocessing et un algorithme de regroupement."""

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", estimator),
        ]
    )


def build_imputer(columns: FeatureColumns) -> ColumnTransformer:
    """Impute uniquement (médiane/numérique, mode/catégoriel) ; ne scale ni n'encode.

    Étape intermédiaire utilisée uniquement quand un ré-échantillonnage
    (SMOTE/SMOTENC/SMOTEN, voir `preprocessing/imbalance.py`) doit s'intercaler
    entre l'imputation et l'encodage — un sur-échantillonneur catégoriel a besoin
    de voir les catégories en clair, pas déjà encodées en one-hot. Sortie en
    DataFrame (colonnes nommées) pour que l'étape d'encodage qui suit puisse
    continuer à sélectionner ses colonnes par nom.
    """

    transformers: list[tuple[str, Any, list[str]]] = []
    if columns.numerical:
        transformers.append(
            ("numerical", SimpleImputer(strategy="median"), list(columns.numerical))
        )
    if columns.categorical:
        transformers.append(
            ("categorical", SimpleImputer(strategy="most_frequent"), list(columns.categorical))
        )
    imputer = ColumnTransformer(
        transformers=transformers, remainder="drop", verbose_feature_names_out=False
    )
    imputer.set_output(transform="pandas")
    return imputer


def build_encoder(columns: FeatureColumns) -> ColumnTransformer:
    """Mise à l'échelle des nombres + encodage one-hot des catégories, sur des
    données déjà imputées (voir `build_imputer`)."""

    transformers: list[tuple[str, Any, list[str]]] = []
    if columns.numerical:
        transformers.append(("numerical", StandardScaler(), list(columns.numerical)))
    if columns.categorical:
        transformers.append(
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                list(columns.categorical),
            )
        )
    return ColumnTransformer(transformers=transformers, remainder="drop")


def build_resampling_pipeline(
    columns: FeatureColumns,
    estimator: BaseEstimator,
    task_type: Literal["classification", "regression"],
    sampler: Any,
    number_of_features: int | Literal["all"] = "all",
) -> ImbalancedPipeline:
    """Comme `build_model_pipeline`, avec un ré-échantillonnage (SMOTE/SMOTENC/SMOTEN)
    inséré entre l'imputation et l'encodage.

    Utilise `imblearn.pipeline.Pipeline`, qui n'applique le ré-échantillonnage que
    pendant `.fit()` — jamais pendant `.predict()`/`.transform()`, ni sur les plis de
    validation d'une cross-validation — donc compatible tel quel avec
    GridSearchCV/RandomizedSearchCV, sans fuite de données. L'étape finale garde le
    nom "preprocessor" pour rester compatible avec
    `explainability/feature_importance.py::resolve_output_feature_names` et
    `training/model_saver.py::save_model`.
    """

    return ImbalancedPipeline(
        steps=[
            ("imputer", build_imputer(columns)),
            ("sampler", sampler),
            ("preprocessor", build_encoder(columns)),
            ("feature_selector", build_feature_selector(task_type, number_of_features)),
            ("model", estimator),
        ]
    )
