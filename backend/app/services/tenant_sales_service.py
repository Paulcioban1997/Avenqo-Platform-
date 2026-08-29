from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy.orm import Session

from backend.app.ai.tools.business.analytics import compute_sales_summary, compute_sales_trend
from backend.app.models import ModelRegistry
from backend.app.services.portfolio_decision_service import (
    PortfolioAnalysisUnavailable,
    build_sales_forecast_signal,
)
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.prediction.service import PredictionService


_SALES_FIELDS = frozenset({"total_amount"})
_VALID_PERIODS = frozenset({"current_month", "last_30_days", "last_90_days", "year_to_date", "custom"})


class InvalidSalesPeriod(ValueError):
    pass


class TenantSalesService:
    def __init__(
        self,
        session: Session,
        analytics: TenantAnalyticsService,
        prediction_service: PredictionService,
    ) -> None:
        self._session = session
        self._analytics = analytics
        self._prediction_service = prediction_service

    def build(
        self,
        tenant: TenantContext,
        *,
        period_key: str = "last_30_days",
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, Any]:
        self._validate_period(period_key, date_from, date_to)
        snapshot = self._analytics.load(tenant)
        source = snapshot.source_for(_SALES_FIELDS)
        base = {
            "status": snapshot.status,
            "available": source is not None,
            "currency": snapshot.currency,
            "capabilities": sorted(snapshot.capabilities),
        }
        if source is None:
            return {
                **base,
                "period": self._empty_period(period_key),
                "summary": None,
                "trend": {"granularity": "month", "points": []},
                "strongest_period": None,
                "weakest_period": None,
                "forecast": None,
            }

        bounds = self._resolve_period(source, period_key, date_from, date_to)
        current = compute_sales_summary(
            source,
            date_from=bounds["start"],
            date_to=bounds["end"],
            product=None,
        )
        previous = (
            compute_sales_summary(
                source,
                date_from=bounds["comparison_start"],
                date_to=bounds["comparison_end"],
                product=None,
            )
            if bounds["comparison_start"] is not None
            else None
        )
        current["revenue_change_percent"] = self._change(
            float(current["revenue"]),
            float(previous["revenue"]) if previous is not None else None,
        )
        current["orders_change_percent"] = self._change(
            int(current["orders"]),
            int(previous["orders"]) if previous is not None else None,
        )
        current["previous_revenue"] = previous["revenue"] if previous is not None else None
        current["previous_orders"] = previous["orders"] if previous is not None else None

        trend = compute_sales_trend(
            source,
            date_from=bounds["start"],
            date_to=bounds["end"],
            granularity=bounds["granularity"],
        )
        points = trend["points"]
        strongest = max(points, key=lambda item: item["revenue"]) if points else None
        weakest = min(points, key=lambda item: item["revenue"]) if points else None
        return {
            **base,
            "period": {"key": period_key, **bounds},
            "summary": current,
            "trend": trend,
            "strongest_period": strongest,
            "weakest_period": weakest,
            "forecast": self._forecast(tenant, snapshot.active_models),
        }

    def _forecast(
        self,
        tenant: TenantContext,
        active_models: tuple[ModelRegistry, ...],
    ) -> dict[str, Any] | None:
        if not any(model.task_code == "weekly_forecast" for model in active_models):
            return None
        try:
            signal = build_sales_forecast_signal(
                self._session,
                tenant,
                "retail",
                self._prediction_service,
            )
        except (PortfolioAnalysisUnavailable, OSError, ValueError, TypeError, KeyError):
            return None
        points = list(signal.metadata.get("forecast_points") or ())
        return {
            "granularity": "week",
            "forecasted_total": signal.value,
            "points": [
                {"period": str(index + 1), "value": value}
                for index, value in enumerate(points)
            ],
        }

    @staticmethod
    def _resolve_period(source, key: str, date_from: date | None, date_to: date | None):
        reverse = {canonical: original for original, canonical in source.canonical_columns.items()}
        date_column = reverse.get("order_timestamp")
        timestamps = []
        if date_column is not None:
            for row in source.rows:
                value = row.get(date_column)
                if isinstance(value, str):
                    try:
                        timestamps.append(datetime.fromisoformat(value))
                    except ValueError:
                        continue
        if not timestamps:
            return {
                "start": None,
                "end": None,
                "comparison_start": None,
                "comparison_end": None,
                "date_filter_available": False,
                "granularity": "month",
            }

        latest = max(timestamps)
        end = latest
        if key == "custom":
            assert date_from is not None and date_to is not None
            start = datetime.combine(date_from, time.min)
            end = datetime.combine(date_to, time.max)
        elif key == "current_month":
            start = latest.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif key == "last_90_days":
            start = latest - timedelta(days=89)
        elif key == "year_to_date":
            start = latest.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start = latest - timedelta(days=29)

        duration = end - start
        comparison_end = start - timedelta(microseconds=1)
        comparison_start = comparison_end - duration
        days = max(1, duration.days + 1)
        granularity = "day" if days <= 31 else "week" if days <= 120 else "month"
        return {
            "start": start,
            "end": end,
            "comparison_start": comparison_start,
            "comparison_end": comparison_end,
            "date_filter_available": True,
            "granularity": granularity,
        }

    @staticmethod
    def _validate_period(key: str, date_from: date | None, date_to: date | None) -> None:
        if key not in _VALID_PERIODS:
            raise InvalidSalesPeriod("Unsupported sales period")
        if key == "custom" and (
            date_from is None or date_to is None or date_from > date_to
        ):
            raise InvalidSalesPeriod("A valid custom date range is required")

    @staticmethod
    def _change(current: float | int, previous: float | int | None) -> float | None:
        if previous in {None, 0}:
            return None
        return round(((current - previous) / previous) * 100, 2)

    @staticmethod
    def _empty_period(key: str) -> dict[str, Any]:
        return {
            "key": key,
            "start": None,
            "end": None,
            "comparison_start": None,
            "comparison_end": None,
            "date_filter_available": False,
            "granularity": "month",
        }