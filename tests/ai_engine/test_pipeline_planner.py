from shared.ai_engine.contracts import BusinessStrategy
from shared.ai_engine.pipelines.planner import AIPipelinePlanner


def test_pipeline_planner_builds_logical_execution_order_from_strategy() -> None:
    planner = AIPipelinePlanner()

    strategy = BusinessStrategy(
        module_code="retail",
        task_family="Forecasting",
        target="Revenue",
        time_column="Order Date",
        granularity="Monthly",
        horizon="12 months",
    )

    plan = planner.plan(strategy)

    assert plan.module_code == "retail"
    assert plan.task_code == "forecasting"
    assert plan.stages == (
        "validate_schema",
        "validate_mapping",
        "validate_dataset_quality",
        "validate_temporal_consistency",
        "prepare_feature_engineering",
        "prepare_ai_engine",
        "prepare_model_registry",
    )
