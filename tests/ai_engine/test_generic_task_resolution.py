from shared.ai_engine.task_resolution.service import TaskResolutionService


def _service() -> TaskResolutionService:
    return TaskResolutionService()


def test_dataset_forecasting_capability_is_detected() -> None:
    rows = [
        {"customer_id": 1, "date": "2024-01-01", "sales": 100.0},
        {"customer_id": 2, "date": "2024-01-02", "sales": 140.0},
        {"customer_id": 3, "date": "2024-01-03", "sales": 180.0},
    ]

    capabilities = _service().resolve_dataset_capabilities(rows)

    assert "forecasting" in capabilities


def test_dataset_classification_capability_is_detected() -> None:
    rows = [
        {"customer_id": 1, "age": 31, "orders": 4, "churn": "no"},
        {"customer_id": 2, "age": 42, "orders": 10, "churn": "yes"},
        {"customer_id": 3, "age": 26, "orders": 3, "churn": "no"},
    ]

    capabilities = _service().resolve_dataset_capabilities(rows)

    assert "classification" in capabilities


def test_dataset_regression_capability_is_detected() -> None:
    rows = [
        {"product_id": 1, "category": "A", "cost": 10.0, "price": 25.0},
        {"product_id": 2, "category": "B", "cost": 12.0, "price": 32.0},
        {"product_id": 3, "category": "A", "cost": 9.0, "price": 28.0},
    ]

    capabilities = _service().resolve_dataset_capabilities(rows)

    assert "regression" in capabilities


def test_dataset_segmentation_capability_is_detected() -> None:
    rows = [
        {"customer_id": 1, "frequency": 7, "monetary_value": 120, "recency": 4},
        {"customer_id": 2, "frequency": 15, "monetary_value": 240, "recency": 2},
        {"customer_id": 3, "frequency": 4, "monetary_value": 70, "recency": 9},
    ]

    capabilities = _service().resolve_dataset_capabilities(rows)

    assert "segmentation" in capabilities


def test_dataset_recommendation_capability_is_detected() -> None:
    rows = [
        {"customer_id": 1, "product_id": 10, "interaction": 1},
        {"customer_id": 1, "product_id": 15, "interaction": 3},
        {"customer_id": 2, "product_id": 10, "interaction": 2},
    ]

    capabilities = _service().resolve_dataset_capabilities(rows)

    assert "recommendation" in capabilities


def test_insufficient_dataset_does_not_invent_ai_task() -> None:
    rows = [{"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}]

    capabilities = _service().resolve_dataset_capabilities(rows)

    assert capabilities == set()


def test_module_capabilities_are_intersected_with_dataset_capabilities() -> None:
    rows = [
        {"customer_id": 1, "date": "2024-01-01", "sales": 100.0},
        {"customer_id": 2, "date": "2024-01-02", "sales": 140.0},
        {"customer_id": 3, "date": "2024-01-03", "sales": 160.0},
    ]

    tasks = _service().resolve_tasks_for_module("retail", rows)

    assert "forecasting" in tasks
