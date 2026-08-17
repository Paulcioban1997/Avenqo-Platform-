from uuid import UUID

import pandas as pd

from shared.ai_engine.contracts import BusinessStrategy
from shared.ai_engine.pipelines.planner import AIPipelinePlanner, PipelinePlan
from shared.ai_engine.feature_engineering.engine import FeatureEngineeringEngine


def _strategy(task_family: str = "Forecasting") -> BusinessStrategy:
    return BusinessStrategy(
        module_code="retail",
        task_family=task_family,
        target="revenue",
        time_column="order_date",
        granularity="Monthly",
        horizon="12 months",
    )


def _pipeline() -> PipelinePlan:
    return AIPipelinePlanner().plan(_strategy())


def test_feature_engineering_builds_plan_for_forecasting() -> None:
    df = pd.DataFrame(
        {
            "customer_id": [1, 2, 3],
            "order_date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "revenue": [100.0, 110.0, 120.0],
            "channel": ["web", "store", "web"],
        }
    )

    engine = FeatureEngineeringEngine()
    plan = engine.build_plan(
        tenant_id=str(UUID("00000000-0000-0000-0000-000000000001")),
        dataset_id="dataset-1",
        dataset_version="v1",
        strategy=_strategy("Forecasting"),
        pipeline=_pipeline(),
        dataset=df,
    )

    assert plan.task_family == "Forecasting"
    assert plan.target == "revenue"
    assert "validate_schema" in _pipeline().stages
    assert "time_ordering" in plan.transformations
    assert "categorical_encoding" in plan.transformations
    assert "no_temporal_leakage" in plan.leakage_constraints


def test_feature_engineering_prepares_dataset_without_leakage() -> None:
    df = pd.DataFrame(
        {
            "order_date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "revenue": [100.0, 120.0, 140.0],
            "region": ["Paris", "Paris", "Lyon"],
        }
    )

    prepared = FeatureEngineeringEngine().prepare(
        tenant_id="tenant-1",
        dataset_id="dataset-2",
        dataset_version="v2",
        strategy=_strategy("Regression"),
        pipeline=_pipeline(),
        dataset=df,
    )

    assert prepared.target_name == "revenue"
    assert prepared.y is not None
    assert prepared.feature_plan.target == "revenue"
    assert prepared.metadata["leakage_protection"] == prepared.feature_plan.leakage_constraints


def test_feature_engineering_handles_categorical_missing_values() -> None:
    df = pd.DataFrame(
        {
            "customer_id": ["a", "b", None],
            "amount": [10.0, 20.0, 30.0],
            "category": ["x", None, "y"],
            "target": [1, 0, 1],
        }
    )

    prepared = FeatureEngineeringEngine().prepare(
        tenant_id="tenant-2",
        dataset_id="dataset-3",
        dataset_version="v3",
        strategy=_strategy("Classification").__class__(
            module_code="retail",
            task_family="Classification",
            target="target",
            time_column=None,
            granularity="Monthly",
            horizon="12 months",
        ),
        pipeline=_pipeline(),
        dataset=df,
    )

    assert prepared.X is not None
    assert prepared.feature_names
    assert prepared.metadata["pipeline_stages"] == _pipeline().stages
