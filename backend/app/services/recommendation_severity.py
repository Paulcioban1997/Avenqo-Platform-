from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RecommendationSeverityAssessment:
    severity: str
    reason: str
    score: float
    absolute_impact: float
    revenue_share: float


@dataclass(frozen=True, slots=True)
class RecommendationSeverityPolicy:
    material_impact: float = 1_000.0
    minimum_high_impact: float = 25.0
    minimum_critical_impact: float = 100.0
    high_revenue_share: float = 0.05
    critical_revenue_share: float = 0.15

    def assess_revenue_change(
        self,
        *,
        current: float,
        previous: float,
        tenant_revenue: float,
    ) -> RecommendationSeverityAssessment:
        absolute_impact = abs(current - previous)
        relative_change = absolute_impact / abs(previous) if previous else 0.0
        revenue_share = absolute_impact / tenant_revenue if tenant_revenue > 0 else 0.0
        score = (
            0.25 * min(1.0, relative_change)
            + 0.25 * min(1.0, absolute_impact / self.material_impact)
            + 0.50 * min(1.0, revenue_share / self.critical_revenue_share)
        )
        critical_floor = max(
            self.minimum_critical_impact,
            tenant_revenue * self.high_revenue_share,
        )
        high_floor = max(
            self.minimum_high_impact,
            tenant_revenue * self.high_revenue_share,
        )
        if (
            score >= 0.75
            and revenue_share >= self.critical_revenue_share
            and absolute_impact >= critical_floor
        ):
            severity, reason = "critical", "material_absolute_and_tenant_share"
        elif score >= 0.55 and absolute_impact >= high_floor:
            severity, reason = "high", "material_revenue_change"
        elif score >= 0.35:
            severity, reason = "medium", "meaningful_relative_or_tenant_share"
        elif score >= 0.15:
            severity, reason = "low", "limited_business_impact"
        else:
            severity, reason = "informational", "minor_business_impact"
        return RecommendationSeverityAssessment(
            severity=severity,
            reason=reason,
            score=round(score, 4),
            absolute_impact=round(absolute_impact, 2),
            revenue_share=round(revenue_share, 4),
        )