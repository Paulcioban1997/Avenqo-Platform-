from backend.app.services.recommendation_severity import RecommendationSeverityPolicy


def test_small_complete_drop_is_not_automatically_critical() -> None:
    result = RecommendationSeverityPolicy().assess_revenue_change(
        current=0,
        previous=5,
        tenant_revenue=5,
    )

    assert result.severity != "critical"
    assert result.absolute_impact == 5


def test_large_material_complete_drop_can_be_critical() -> None:
    result = RecommendationSeverityPolicy().assess_revenue_change(
        current=0,
        previous=100_000,
        tenant_revenue=100_000,
    )

    assert result.severity == "critical"
    assert result.reason == "material_absolute_and_tenant_share"


def test_severity_policy_is_configurable_and_deterministic() -> None:
    policy = RecommendationSeverityPolicy(
        material_impact=500,
        minimum_high_impact=10,
        minimum_critical_impact=50,
    )

    first = policy.assess_revenue_change(
        current=100,
        previous=1_000,
        tenant_revenue=2_000,
    )
    second = policy.assess_revenue_change(
        current=100,
        previous=1_000,
        tenant_revenue=2_000,
    )

    assert first == second