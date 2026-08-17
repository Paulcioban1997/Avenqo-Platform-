from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

import pandas as pd

from shared.ai_engine.contracts import (
    BusinessStrategy,
    FeatureEngineeringPlan,
    PreparedFeatureDataset,
)

if TYPE_CHECKING:
    from shared.ai_engine.pipelines.planner import PipelinePlan


@dataclass(frozen=True, slots=True)
class FeatureEngineeringEngine:
    """Prépare les variables en suivant la stratégie métier et le plan logique.

    Cette couche ne sélectionne pas de modèle et ne construit pas l'AI Engine. Elle
    transforme uniquement un dataset canonique en variables exploitables pour la
    prochaine étape d'exécution.
    """

    def build_plan(
        self,
        tenant_id: str,
        dataset_id: str,
        dataset_version: str,
        strategy: BusinessStrategy,
        pipeline: PipelinePlan,
        dataset: pd.DataFrame,
    ) -> FeatureEngineeringPlan:
        columns = tuple(dataset.columns)
        target = strategy.target
        numeric = tuple(
            column for column in dataset.select_dtypes(include="number").columns if column != target
        )
        categorical = tuple(
            column for column in dataset.columns if column not in numeric and column != target
        )

        datetime_columns = tuple(
            column
            for column in dataset.columns
            if pd.api.types.is_datetime64_any_dtype(dataset[column])
            or self._looks_like_datetime(dataset[column])
        )
        text_columns = tuple(
            column for column in dataset.columns if self._looks_like_text(dataset[column])
        )
        identifiers = tuple(column for column in columns if column.lower().endswith(("id", "uuid")))

        excluded = ()
        if target is not None and target in columns:
            excluded = (target,)

        transformations = tuple(
            self._select_transformations(
                strategy.task_family,
                numeric,
                categorical,
                datetime_columns,
                target=target,
            )
        )

        if dataset.empty or dataset.shape[1] == 0:
            raise ValueError("Feature Engineering requires a non-empty dataset with at least one column.")

        task_family = strategy.task_family.lower().replace("-", " ").replace("_", " ")
        if task_family == "forecasting":
            if not strategy.time_column:
                raise ValueError("Forecasting requires a BusinessStrategy.time_column.")
            if strategy.time_column not in dataset.columns:
                raise ValueError(
                    f"Forecasting requires time_column '{strategy.time_column}' to exist in the canonical dataset."
                )
            if strategy.target is not None and strategy.target not in dataset.columns:
                raise ValueError(
                    f"BusinessStrategy.target '{strategy.target}' does not exist in the canonical dataset."
                )
        elif task_family in {"classification", "regression"}:
            if strategy.target is None:
                raise ValueError(f"{strategy.task_family} requires a BusinessStrategy.target.")
            if strategy.target not in dataset.columns:
                raise ValueError(
                    f"BusinessStrategy.target '{strategy.target}' does not exist in the canonical dataset."
                )

        return FeatureEngineeringPlan(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            module_code=strategy.module_code,
            task_family=strategy.task_family,
            target=target,
            excluded_columns=excluded,
            numerical_columns=numeric,
            categorical_columns=categorical,
            datetime_columns=datetime_columns,
            text_columns=text_columns,
            identifier_columns=identifiers,
            transformations=transformations,
            temporal_features=tuple(
                feature for feature in datetime_columns if feature in (strategy.time_column or ())
            ),
            aggregation_features=(),
            missing_value_strategy="median_for_numeric;most_frequent_for_categorical",
            encoding_strategy="one_hot_for_categorical",
            scaling_requirement=bool(numeric),
            leakage_constraints=(
                "no_target_leakage",
                "no_future_information_leakage",
                "no_temporal_leakage",
                "tenant_boundaries_only",
            ),
            fit_transform_safe=True,
            output_schema=tuple(columns),
            metadata={
                "pipeline_stages": pipeline.stages,
                "time_column": strategy.time_column,
                "granularity": strategy.granularity,
                "horizon": strategy.horizon,
                "fit_transform_safe": True,
            },
        )

    def prepare(
        self,
        tenant_id: str,
        dataset_id: str,
        dataset_version: str,
        strategy: BusinessStrategy,
        pipeline: PipelinePlan,
        dataset: pd.DataFrame,
    ) -> PreparedFeatureDataset:
        plan = self.build_plan(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            strategy=strategy,
            pipeline=pipeline,
            dataset=dataset,
        )

        features = dataset.copy()
        task_family = strategy.task_family.lower().replace("-", " ").replace("_", " ")
        if task_family in {"classification", "regression", "forecasting"}:
            if not strategy.target:
                raise ValueError(f"{strategy.task_family} requires a BusinessStrategy.target.")
            if strategy.target not in features.columns:
                raise ValueError(
                    f"BusinessStrategy.target '{strategy.target}' does not exist in the canonical dataset."
                )
            target_series = features[strategy.target]
            X = features.drop(columns=[strategy.target])
            y = target_series
        else:
            X = features
            y = None

        numeric_columns = [column for column in plan.numerical_columns if column in X.columns]
        categorical_columns = [column for column in plan.categorical_columns if column in X.columns]
        feature_names = tuple(X.columns)
        feature_types = {
            column: self._infer_type(X[column])
            for column in X.columns
        }

        if numeric_columns:
            X[numeric_columns] = X[numeric_columns].apply(pd.to_numeric, errors="coerce")
            X[numeric_columns] = X[numeric_columns].fillna(X[numeric_columns].median())

        if categorical_columns:
            X[categorical_columns] = X[categorical_columns].fillna("missing")

        return PreparedFeatureDataset(
            tenant_id=tenant_id,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            module_code=strategy.module_code,
            task_family=strategy.task_family,
            X=X,
            y=y,
            feature_names=feature_names,
            feature_types=feature_types,
            target_name=strategy.target,
            feature_plan=plan,
            metadata={
                "pipeline_stages": pipeline.stages,
                "time_column": strategy.time_column,
                "granularity": strategy.granularity,
                "horizon": strategy.horizon,
                "leakage_protection": plan.leakage_constraints,
                "fit_transform_safe": plan.fit_transform_safe,
            },
        )

    @staticmethod
    def _looks_like_datetime(series: pd.Series) -> bool:
        sample = series.dropna().head(10)
        if sample.empty:
            return False
        try:
            pd.to_datetime(sample, errors="raise", format="mixed")
            return True
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _looks_like_text(series: pd.Series) -> bool:
        non_null = series.dropna().astype(str)
        if non_null.empty:
            return False
        text_like = non_null.str.len().gt(2).mean()
        return bool(text_like > 0.5)

    @staticmethod
    def _infer_type(series: pd.Series) -> str:
        if pd.api.types.is_numeric_dtype(series):
            return "numeric"
        if pd.api.types.is_datetime64_any_dtype(series):
            return "datetime"
        return "categorical"

    @staticmethod
    def _select_transformations(
        task_family: str,
        numeric: tuple[str, ...],
        categorical: tuple[str, ...],
        datetime_columns: tuple[str, ...],
        *,
        target: str | None,
    ) -> tuple[str, ...]:
        base = ["missing_value_handling", "type_coercion"]
        if numeric:
            base.append("numeric_scaling")
        if categorical:
            base.append("categorical_encoding")
        if datetime_columns:
            base.append("datetime_feature_expansion")

        family = task_family.lower().replace("-", " ").replace("_", " ")
        if family == "forecasting":
            base.extend(["time_ordering", "lag_features", "rolling_statistics"])
        elif family in {"customer segmentation", "recommendation"}:
            base.extend(["aggregation_features", "behavioral_summary"])
        elif family == "anomaly detection":
            base.extend(["delta_features", "deviation_normalization", "rolling_statistics"])
        elif family in {"classification", "regression"}:
            base.extend(["interaction_features", "distribution_aware_preparation"])

        if target is not None:
            base.append("target_separation")
        return tuple(dict.fromkeys(base))
