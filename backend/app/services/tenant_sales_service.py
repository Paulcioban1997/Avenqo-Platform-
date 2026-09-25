from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.app.ai.tools.business.analytics import (
    compute_sales_summary,
    compute_sales_trend,
    parse_business_datetime,
)
from backend.app.services.portfolio_decision_service import (
    PortfolioAnalysisUnavailable,
    build_sales_forecast_signal,
)
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from shared.ai_engine.contracts import TenantContext
from shared.ai_engine.prediction.service import PredictionService


_SALES_FIELDS = frozenset({"total_amount"})
_VALID_PERIODS = frozenset({
    "all",
    "last_7_days",
    "last_30_days",
    "current_quarter",
    "current_month",
    "last_90_days",
    "year_to_date",
    "custom",
})


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
        if (
            source is not None
            and snapshot.active_source_provider == "shopify"
            and not self._has_shopify_orders(source)
        ):
            source = None
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
            "forecast": self._forecast(tenant, snapshot),
        }

    @staticmethod
    def _has_shopify_orders(source) -> bool:
        order_column = next(
            (
                original
                for original, canonical in source.canonical_columns.items()
                if canonical == "order_id"
            ),
            None,
        )
        return bool(
            order_column
            and any(str(row.get(order_column) or "").strip() for row in source.rows)
        )

    def _forecast(
        self,
        tenant: TenantContext,
        snapshot,
    ) -> dict[str, Any] | None:
        if any(model.task_code == "weekly_forecast" for model in snapshot.active_models):
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
                "method": "trained_model",
                "forecasted_total": signal.value,
                "points": [
                    {"period": str(index + 1), "value": value}
                    for index, value in enumerate(points)
                ],
            }

        source = snapshot.source_for(frozenset({"total_amount", "order_timestamp"}))
        if source is None:
            return None
        today = datetime.now(timezone.utc)
        history = compute_sales_trend(
            source,
            date_from=today - timedelta(days=28),
            date_to=today,
            granularity="week",
        )["points"]
        observations = [float(point["revenue"]) for point in history[-4:]]
        if len(observations) < 2:
            return None
        weekly_baseline = sum(observations) / len(observations)
        forecast_points = [round(weekly_baseline, 2)] * 4
        return {
            "granularity": "week",
            "method": "historical_weekly_mean",
            "horizon": 4,
            "forecasted_total": round(sum(forecast_points), 2),
            "points": [
                {"period": str(index + 1), "value": value}
                for index, value in enumerate(forecast_points)
            ],
        }

    @staticmethod
    def _resolve_period(source, key: str, date_from: date | None, date_to: date | None):
        reverse = {canonical: original for original, canonical in source.canonical_columns.items()}
        date_column = reverse.get("order_timestamp")
        timestamps = []
        if date_column is not None:
            for row in source.rows:
                timestamp = parse_business_datetime(row.get(date_column))
                if timestamp is not None:
                    timestamps.append(
                        timestamp.replace(tzinfo=timezone.utc)
                        if timestamp.tzinfo is None
                        else timestamp.astimezone(timezone.utc)
                    )
        now = datetime.now(timezone.utc)
        if key == "all":
            return {
                "start": min(timestamps) if timestamps else None,
                "end": max(timestamps) if timestamps else None,
                "comparison_start": None,
                "comparison_end": None,
                "date_filter_available": bool(timestamps),
                "granularity": "month",
            }

        if key == "custom":
            assert date_from is not None and date_to is not None
            start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
            end = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
        elif key == "last_7_days":
            start = now - timedelta(days=7)
            end = now
        elif key == "last_30_days":
            start = now - timedelta(days=30)
            end = now
        elif key == "current_quarter":
            quarter_month = ((now.month - 1) // 3) * 3 + 1
            start = now.replace(
                month=quarter_month,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            end = now
        elif key == "current_month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif key == "last_90_days":
            start = now - timedelta(days=90)
            end = now
        elif key == "year_to_date":
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start = now - timedelta(days=30)
        if key not in {"custom", "last_90_days"}:
            end = now

        start = TenantSalesService._as_utc(start)
        end = TenantSalesService._as_utc(end)

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
            "date_filter_available": bool(date_column and timestamps),
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

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )