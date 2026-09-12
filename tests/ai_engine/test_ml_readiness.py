from shared.ai_engine.dataset_ingestion.ml_readiness import assess_ml_readiness


def test_small_commerce_dataset_is_not_ready_for_ml() -> None:
    rows = [{"order_id": str(index), "bad_review": index % 2} for index in range(6)]

    readiness = assess_ml_readiness(
        rows, family="classification", target_column="bad_review"
    )

    assert readiness.ready is False
    assert readiness.code == "DATASET_NOT_READY_FOR_ML"
    assert "minimum_samples:20" in readiness.reasons


def test_balanced_feature_ready_dataset_can_train() -> None:
    rows = [
        {"order_id": str(index), "bad_review": index % 2, "amount": index + 1}
        for index in range(20)
    ]

    readiness = assess_ml_readiness(
        rows, family="classification", target_column="bad_review"
    )

    assert readiness.ready is True


def test_missing_or_constant_target_is_rejected() -> None:
    rows = [
        {"order_id": str(index), "target": None if index == 0 else 1}
        for index in range(20)
    ]

    readiness = assess_ml_readiness(rows, family="regression", target_column="target")

    assert readiness.ready is False
    assert "target_missing_values" in readiness.reasons
    assert "target_has_no_variation" in readiness.reasons