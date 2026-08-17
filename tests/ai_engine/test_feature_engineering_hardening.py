from __future__ import annotations

from uuid import UUID

import pandas as pd
import pytest

from shared.ai_engine.contracts import BusinessStrategy
from shared.ai_engine.feature_engineering.engine import FeatureEngineeringEngine
from shared.ai_engine.pipelines.planner import AIPipelinePlanner


def _strategy(task_family: str, *, target: str | None = None, time_column: str | None = None) -> BusinessStrategy:
    return BusinessStrategy(
        module_code="retail",
        task_family=task_family,
        target=target,
        time_column=time_column,
        granularity="Monthly",
        horizon="12 months",
    )


def _pipeline(task_family: str, *, target: str | None = None, time_column: str | None = None):
    return AIPipelinePlanner().plan(_strategy(task_family, target=target, time_column=time_column))


def test_classification_prepares_x_and_y_without_target_leakage() -> None:
    df = pd.DataFrame(
        {
            "customer_id": ["A", "B", "C", "D"],
            "income": [10.0, 15.0, 20.0, 25.0],
            "segment": ["low", "low", "high", "high"],
            "target": [0, 1, 1, 0],
        }
    )

    strategy = _strategy("Classification", target="target")
    prepared = FeatureEngineeringEngine().prepare(
        tenant_id=str(UUID("00000000-0000-0000-0000-000000000011")),
        dataset_id="ds-class",
        dataset_version="v1",
        strategy=strategy,
        pipeline=_pipeline("Classification", target="target"),
        dataset=df,
    )

    assert prepared.target_name == "target"
    assert prepared.y is not None
    assert "target" not in prepared.X.columns
    assert prepared.X.shape[1] == 3


def test_regression_prepares_numeric_targets_without_leakage() -> None:
    df = pd.DataFrame(
        {
            "customer_id": ["A", "B", "C"],
            "age": [25, 35, 45],
            "region": ["east", "west", "east"],
            "revenue": [120.0, 200.0, 240.0],
        }
    )

    prepared = FeatureEngineeringEngine().prepare(
        tenant_id="tenant-reg",
        dataset_id="ds-reg",
        dataset_version="v1",
        strategy=_strategy("Regression", target="revenue"),
        pipeline=_pipeline("Regression", target="revenue"),
        dataset=df,
    )

    assert prepared.target_name == "revenue"
    assert prepared.y is not None
    assert "revenue" not in prepared.X.columns
    assert prepared.feature_plan.output_schema == tuple(df.columns)


def test_forecasting_keeps_time_order_and_horizon_constraints() -> None:
    df = pd.DataFrame(
        {
            "order_date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]),
            "revenue": [100.0, 120.0, 135.0],
            "channel": ["web", "web", "store"],
        }
    )

    strategy = _strategy("Forecasting", target="revenue", time_column="order_date")
    prepared = FeatureEngineeringEngine().prepare(
        tenant_id="tenant-forecast",
        dataset_id="ds-forecast",
        dataset_version="v1",
        strategy=strategy,
        pipeline=_pipeline("Forecasting", target="revenue", time_column="order_date"),
        dataset=df,
    )

    assert prepared.feature_plan.task_family == "Forecasting"
    assert prepared.feature_plan.temporal_features == ("order_date",)
    assert prepared.metadata["time_column"] == "order_date"
    assert prepared.metadata["horizon"] == "12 months"
    assert "time_ordering" in prepared.feature_plan.transformations
    assert "no_future_information_leakage" in prepared.feature_plan.leakage_constraints


def test_customer_segmentation_prepares_unlabelled_dataset_without_supervised_target() -> None:
    df = pd.DataFrame(
        {
            "customer_id": ["c1", "c2", "c3"],
            "recency_days": [10, 20, 35],
            "frequency": [5, 4, 3],
            "monetary": [100.0, 80.0, 50.0],
        }
    )

    prepared = FeatureEngineeringEngine().prepare(
        tenant_id="tenant-seg",
        dataset_id="ds-seg",
        dataset_version="v1",
        strategy=_strategy("Customer Segmentation"),
        pipeline=_pipeline("Customer Segmentation"),
        dataset=df,
    )

    assert prepared.y is None
    assert prepared.X.shape[1] == 4
    assert prepared.feature_plan.task_family == "Customer Segmentation"


def test_recommendation_prepares_entity_and_interaction_data() -> None:
    df = pd.DataFrame(
        {
            "user_id": [1, 1, 2],
            "product_id": [10, 11, 10],
            "interaction_score": [0.8, 0.7, 0.5],
        }
    )

    prepared = FeatureEngineeringEngine().prepare(
        tenant_id="tenant-rec",
        dataset_id="ds-rec",
        dataset_version="v1",
        strategy=_strategy("Recommendation"),
        pipeline=_pipeline("Recommendation"),
        dataset=df,
    )

    assert prepared.y is None
    assert prepared.X.shape[1] == 3
    assert prepared.feature_plan.task_family == "Recommendation"


def test_anomaly_detection_prepares_unlabelled_dataset() -> None:
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "metric_a": [1.0, 1.1, 1.2],
            "metric_b": [2.0, 2.1, 2.2],
        }
    )

    prepared = FeatureEngineeringEngine().prepare(
        tenant_id="tenant-anom",
        dataset_id="ds-anom",
        dataset_version="v1",
        strategy=_strategy("Anomaly Detection"),
        pipeline=_pipeline("Anomaly Detection"),
        dataset=df,
    )

    assert prepared.y is None
    assert prepared.feature_plan.task_family == "Anomaly Detection"
    assert "delta_features" in prepared.feature_plan.transformations


def test_empty_dataset_raises_clear_business_error() -> None:
    empty = pd.DataFrame()

    with pytest.raises(ValueError, match="non-empty dataset"):
        FeatureEngineeringEngine().build_plan(
            tenant_id="tenant-empty",
            dataset_id="ds-empty",
            dataset_version="v1",
            strategy=_strategy("Classification", target="label"),
            pipeline=_pipeline("Classification", target="label"),
            dataset=empty,
        )


def test_missing_target_raises_clear_business_error() -> None:
    df = pd.DataFrame({"feature_a": [1, 2, 3]})

    with pytest.raises(ValueError, match="target"):
        FeatureEngineeringEngine().prepare(
            tenant_id="tenant-missing-target",
            dataset_id="ds-missing-target",
            dataset_version="v1",
            strategy=_strategy("Classification", target="missing_target"),
            pipeline=_pipeline("Classification", target="missing_target"),
            dataset=df,
        )


def test_missing_time_column_for_forecasting_raises_clear_business_error() -> None:
    df = pd.DataFrame({"revenue": [100.0, 110.0, 120.0]})

    with pytest.raises(ValueError, match="time_column"):
        FeatureEngineeringEngine().prepare(
            tenant_id="tenant-missing-time",
            dataset_id="ds-missing-time",
            dataset_version="v1",
            strategy=_strategy("Forecasting", target="revenue", time_column="order_date"),
            pipeline=_pipeline("Forecasting", target="revenue", time_column="order_date"),
            dataset=df,
        )


def test_unknown_columns_are_left_in_schema_without_crashing_pipeline() -> None:
    df = pd.DataFrame({
        "unknown_column": ["x", "y", "z"],
        "value": [10.0, 11.0, 12.0],
    })

    prepared = FeatureEngineeringEngine().prepare(
        tenant_id="tenant-unknown",
        dataset_id="ds-unknown",
        dataset_version="v1",
        strategy=_strategy("Regression", target="value"),
        pipeline=_pipeline("Regression", target="value"),
        dataset=df,
    )

    assert prepared.feature_plan.output_schema == tuple(df.columns)
    assert prepared.target_name == "value"


def test_tenant_isolation_prevents_cross_tenant_reuse() -> None:
    tenant_a = pd.DataFrame({"customer_id": ["a1"], "amount": [10.0], "target": [1]})
    tenant_b = pd.DataFrame({"customer_id": ["b1"], "amount": [50.0], "target": [0]})

    prepared_a = FeatureEngineeringEngine().prepare(
        tenant_id="tenant-a",
        dataset_id="ds-a",
        dataset_version="v1",
        strategy=_strategy("Classification", target="target"),
        pipeline=_pipeline("Classification", target="target"),
        dataset=tenant_a,
    )
    prepared_b = FeatureEngineeringEngine().prepare(
        tenant_id="tenant-b",
        dataset_id="ds-b",
        dataset_version="v1",
        strategy=_strategy("Classification", target="target"),
        pipeline=_pipeline("Classification", target="target"),
        dataset=tenant_b,
    )

    assert prepared_a.tenant_id != prepared_b.tenant_id
    assert prepared_a.dataset_id != prepared_b.dataset_id
    assert prepared_a.feature_plan.tenant_id != prepared_b.feature_plan.tenant_id


def test_reproducibility_keeps_feature_schema_consistent() -> None:
    df = pd.DataFrame(
        {
            "order_date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "customer_id": ["c1", "c2", "c3"],
            "revenue": [100.0, 110.0, 120.0],
            "region": ["north", "south", "north"],
        }
    )
    strategy = _strategy("Regression", target="revenue")

    first = FeatureEngineeringEngine().prepare(
        tenant_id="tenant-repeat",
        dataset_id="ds-repeat",
        dataset_version="v1",
        strategy=strategy,
        pipeline=_pipeline("Regression", target="revenue"),
        dataset=df,
    )
    second = FeatureEngineeringEngine().prepare(
        tenant_id="tenant-repeat",
        dataset_id="ds-repeat",
        dataset_version="v1",
        strategy=strategy,
        pipeline=_pipeline("Regression", target="revenue"),
        dataset=df,
    )

    assert first.feature_names == second.feature_names
    assert first.feature_plan.output_schema == second.feature_plan.output_schema
    assert first.feature_plan.metadata["pipeline_stages"] == second.feature_plan.metadata["pipeline_stages"]


def test_target_leakage_is_excluded_from_feature_matrix() -> None:
    df = pd.DataFrame({"feature_a": [1, 2, 3], "feature_b": [4, 5, 6], "target": [1, 0, 1]})
    prepared = FeatureEngineeringEngine().prepare(
        tenant_id="tenant-leak",
        dataset_id="ds-leak",
        dataset_version="v1",
        strategy=_strategy("Classification", target="target"),
        pipeline=_pipeline("Classification", target="target"),
        dataset=df,
    )

    assert "target" not in prepared.X.columns
    assert prepared.y is not None


def test_temporal_leakage_is_protected_in_forecasting_strategy() -> None:
    df = pd.DataFrame(
        {
            "order_date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"]),
            "revenue": [100.0, 110.0, 120.0, 130.0],
            "future_signal": [50.0, 60.0, 70.0, 80.0],
        }
    )

    strategy = _strategy("Forecasting", target="revenue", time_column="order_date")
    prepared = FeatureEngineeringEngine().prepare(
        tenant_id="tenant-temporal",
        dataset_id="ds-temporal",
        dataset_version="v1",
        strategy=strategy,
        pipeline=_pipeline("Forecasting", target="revenue", time_column="order_date"),
        dataset=df,
    )

    assert "no_future_information_leakage" in prepared.feature_plan.leakage_constraints
    assert prepared.feature_plan.temporal_features == ("order_date",)
