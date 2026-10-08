from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.app.ai.tools.business.analytics import (
    compute_business_overview,
    compute_customer_portfolio,
    compute_sales_summary,
    compute_sales_trend,
    compute_top_products,
    filter_rows_by_date,
    parse_business_datetime,
    with_dataset_rows,
)
from backend.app.services.data_freshness_service import DataFreshnessService
from shared.ai_engine.dataset_ingestion.prepared_dataset import PreparedCompanyDataset


_SUPPORTED_PERIODS = frozenset({
    "all", "today", "yesterday", "this_week", "last_week", "last_7_days",
    "last_30_days", "last_90_days", "this_month", "last_month",
    "current_month", "current_quarter", "last_quarter", "year_to_date", "custom",
})


class BusinessMetricsService:
    """Canonical period, timezone and metric envelope over prepared tenant data."""

    def __init__(self, freshness: DataFreshnessService | None = None) -> None:
        self._freshness = freshness or DataFreshnessService()

    @staticmethod
    def normalize_source_timezone(
        source: PreparedCompanyDataset,
        timezone_name: str,
    ) -> PreparedCompanyDataset:
        try:
            business_zone = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            business_zone = ZoneInfo("UTC")
        timestamp_columns = [
            original
            for original, canonical in source.canonical_columns.items()
            if canonical == "order_timestamp"
        ]
        if not timestamp_columns:
            return source
        rows = []
        for row in source.rows:
            normalized = dict(row)
            for column in timestamp_columns:
                parsed = parse_business_datetime(row.get(column))
                if parsed is None:
                    continue
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=business_zone)
                normalized[column] = parsed.astimezone(timezone.utc).isoformat()
            rows.append(normalized)
        return PreparedCompanyDataset(
            company_id=source.company_id,
            dataset_id=source.dataset_id,
            version=source.version,
            canonical_columns=source.canonical_columns,
            rows=tuple(rows),
            profile=source.profile,
            mapping=source.mapping,
            cleaning_report=source.cleaning_report,
            quality=source.quality,
            capability_readiness=source.capability_readiness,
        )

    @staticmethod
    def resolve_period(
        period_key: str | None,
        *,
        timezone_name: str,
        now: datetime | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        source: PreparedCompanyDataset | None = None,
    ) -> dict[str, datetime | None]:
        key = period_key or "last_30_days"
        if key not in _SUPPORTED_PERIODS:
            raise ValueError("Unsupported business metrics period")
        try:
            business_zone = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            business_zone = ZoneInfo("UTC")
        now_utc = BusinessMetricsService._utc(now or datetime.now(timezone.utc))
        now_local = now_utc.astimezone(business_zone)
        today = now_local.date()
        midnight = time.min

        if period_key is None:
            timestamps = BusinessMetricsService._timestamps(source, timezone_name)
            if timestamps:
                end = max(timestamps)
                start = end - timedelta(days=29)
                comparison_end = start - timedelta(microseconds=1)
                comparison_start = comparison_end - timedelta(days=29)
                return {"start": start, "end": end, "comparison_start": comparison_start, "comparison_end": comparison_end}
            return {"start": None, "end": None, "comparison_start": None, "comparison_end": None}
        if key == "all":
            timestamps = BusinessMetricsService._timestamps(source, timezone_name)
            return {
                "start": min(timestamps) if timestamps else None,
                "end": max(timestamps) if timestamps else None,
                "comparison_start": None,
                "comparison_end": None,
            }
        if key == "custom":
            if date_from is None or date_to is None or date_from > date_to:
                raise ValueError("A valid custom date range is required")
            start_local = datetime.combine(date_from, midnight, business_zone)
            end_local = datetime.combine(date_to, time.max, business_zone)
        elif key == "today":
            start_local = datetime.combine(today, midnight, business_zone)
            end_local = now_local
        elif key == "yesterday":
            start_local = datetime.combine(today - timedelta(days=1), midnight, business_zone)
            end_local = datetime.combine(today, midnight, business_zone) - timedelta(microseconds=1)
        elif key == "this_week":
            start_local = datetime.combine(today - timedelta(days=today.weekday()), midnight, business_zone)
            end_local = now_local
        elif key == "last_week":
            this_week = today - timedelta(days=today.weekday())
            start_local = datetime.combine(this_week - timedelta(days=7), midnight, business_zone)
            end_local = datetime.combine(this_week, midnight, business_zone) - timedelta(microseconds=1)
        elif key in {"this_month", "current_month"}:
            start_local = datetime.combine(today.replace(day=1), midnight, business_zone)
            end_local = now_local
        elif key == "last_month":
            this_month = today.replace(day=1)
            previous_month_end = this_month - timedelta(days=1)
            start_local = datetime.combine(previous_month_end.replace(day=1), midnight, business_zone)
            end_local = datetime.combine(this_month, midnight, business_zone) - timedelta(microseconds=1)
        elif key in {"current_quarter", "last_quarter"}:
            quarter_month = ((today.month - 1) // 3) * 3 + 1
            this_quarter = today.replace(month=quarter_month, day=1)
            if key == "current_quarter":
                start_local = datetime.combine(this_quarter, midnight, business_zone)
                end_local = now_local
            else:
                previous_quarter_end = this_quarter - timedelta(days=1)
                previous_quarter_start = previous_quarter_end.replace(
                    month=((previous_quarter_end.month - 1) // 3) * 3 + 1,
                    day=1,
                )
                start_local = datetime.combine(previous_quarter_start, midnight, business_zone)
                end_local = datetime.combine(this_quarter, midnight, business_zone) - timedelta(microseconds=1)
        elif key == "year_to_date":
            start_local = datetime.combine(today.replace(month=1, day=1), midnight, business_zone)
            end_local = now_local
        else:
            days = {"last_7_days": 7, "last_30_days": 30, "last_90_days": 90}[key]
            start_local = now_local - timedelta(days=days)
            end_local = now_local

        start = start_local.astimezone(timezone.utc)
        end = end_local.astimezone(timezone.utc)
        if key in {"today", "yesterday"}:
            comparison_start_local = start_local - timedelta(days=1)
            comparison_end_local = end_local - timedelta(days=1)
        elif key in {"this_week", "last_week"}:
            comparison_start_local = start_local - timedelta(days=7)
            comparison_end_local = end_local - timedelta(days=7)
        elif key in {"this_month", "current_month"}:
            comparison_start_local = BusinessMetricsService._shift_month(start_local, -1)
            comparison_end_local = BusinessMetricsService._shift_month(end_local, -1)
        elif key == "last_month":
            comparison_start_local = BusinessMetricsService._shift_month(start_local, -1)
            comparison_end_local = start_local - timedelta(microseconds=1)
        elif key == "current_quarter":
            comparison_start_local = BusinessMetricsService._shift_month(start_local, -3)
            comparison_end_local = BusinessMetricsService._shift_month(end_local, -3)
        elif key == "last_quarter":
            comparison_start_local = BusinessMetricsService._shift_month(start_local, -3)
            comparison_end_local = start_local - timedelta(microseconds=1)
        elif key == "year_to_date":
            comparison_start_local = BusinessMetricsService._shift_month(start_local, -12)
            comparison_end_local = BusinessMetricsService._shift_month(end_local, -12)
        else:
            comparison_end_local = start_local - timedelta(microseconds=1)
            comparison_start_local = comparison_end_local - (end_local - start_local)
        comparison_start = comparison_start_local.astimezone(timezone.utc)
        comparison_end = comparison_end_local.astimezone(timezone.utc)
        return {
            "start": start,
            "end": end,
            "comparison_start": comparison_start,
            "comparison_end": comparison_end,
        }

    def sales_summary(
        self,
        snapshot,
        source: PreparedCompanyDataset,
        *,
        period_start: datetime | None,
        period_end: datetime | None,
        product: str | None = None,
        queried_at: datetime | None = None,
    ) -> dict[str, Any]:
        calculated_at = self._utc(queried_at or datetime.now(timezone.utc))
        normalized = self.normalize_source_timezone(
            source, getattr(snapshot.company, "timezone", None) or "UTC"
        )
        summary = compute_sales_summary(
            normalized,
            date_from=period_start,
            date_to=period_end,
            product=product,
        )
        freshness = self._freshness.for_snapshot(snapshot, queried_at=calculated_at)
        tz_name = getattr(snapshot.company, "timezone", None) or "UTC"
        timestamps = self._timestamps(normalized, tz_name)
        max_trans_time = max(timestamps) if timestamps else None
        last_sync = freshness.last_updated_at
        latest_coverage = max(filter(None, [max_trans_time, last_sync]), default=None)

        data_covered = True
        coverage_message = None
        if period_start is not None and latest_coverage is not None:
            latest_coverage_utc = self._utc(latest_coverage)
            period_start_utc = self._utc(period_start)
            if period_start_utc.date() > latest_coverage_utc.date() or (
                period_start_utc > latest_coverage_utc
                and summary.get("rows_considered", 0) == 0
                and freshness.freshness_status in {"STALE", "UNAVAILABLE"}
            ):
                data_covered = False
                month_names_fr = {
                    1: "janvier", 2: "février", 3: "mars", 4: "avril",
                    5: "mai", 6: "juin", 7: "juillet", 8: "août",
                    9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
                }
                sync_d = latest_coverage_utc.date()
                target_d = period_start_utc.date()
                sync_str = f"{sync_d.day} {month_names_fr.get(sync_d.month, '')}"
                target_str = f"{target_d.day} {month_names_fr.get(target_d.month, '')}"
                coverage_message = f"Les données disponibles s'arrêtent au {sync_str} ; je ne peux pas confirmer les commandes du {target_str}."

        if not data_covered:
            summary["data_covered"] = False
            summary["coverage_message"] = coverage_message
            metrics = [
                self.metric_envelope(snapshot, source, "revenue", None, "currency", period_start, period_end, None, calculated_at=calculated_at, state="DATA_UNCOVERED"),
                self.metric_envelope(snapshot, source, "orders", None, "count", period_start, period_end, None, calculated_at=calculated_at, state="DATA_UNCOVERED"),
                self.metric_envelope(snapshot, source, "average_order_value", None, "currency", period_start, period_end, None, calculated_at=calculated_at, state="DATA_UNCOVERED"),
            ]
        else:
            summary["data_covered"] = True
            summary["coverage_message"] = None
            metrics = [
                self.metric_envelope(snapshot, source, "revenue", summary["revenue"], "currency", period_start, period_end, summary["orders"], calculated_at=calculated_at, state="AVAILABLE" if summary["rows_considered"] else "INSUFFICIENT_DATA"),
                self.metric_envelope(snapshot, source, "orders", summary["orders"], "count", period_start, period_end, summary["orders"], calculated_at=calculated_at, state="AVAILABLE" if summary["orders"] else "INSUFFICIENT_DATA"),
                self.metric_envelope(snapshot, source, "average_order_value", summary["average_order_value"], "currency", period_start, period_end, summary["orders"], calculated_at=calculated_at, state="AVAILABLE" if summary["orders"] else "INSUFFICIENT_DATA"),
            ]
        return {**summary, "metrics": metrics, "data_freshness": freshness.as_dict()}

    def business_overview(
        self,
        snapshot,
        source: PreparedCompanyDataset,
        *,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        queried_at: datetime | None = None,
    ) -> dict[str, Any]:
        calculated_at = self._utc(queried_at or datetime.now(timezone.utc))
        normalized = self.normalize_source_timezone(
            source, getattr(snapshot.company, "timezone", None) or "UTC"
        )
        reverse = {canonical: original for original, canonical in normalized.canonical_columns.items()}
        rows = filter_rows_by_date(normalized.rows, reverse, period_start, period_end)
        selected_rows = with_dataset_rows(normalized, rows)
        sales = compute_sales_summary(
            selected_rows,
            date_from=None,
            date_to=None,
            product=None,
        )
        customer_summary = compute_business_overview(selected_rows)
        overview = {
            "period": customer_summary["period"],
            "revenue": sales["revenue"],
            "orders": sales["orders"],
            "customers": customer_summary["customers"],
            "average_order_value": sales["average_order_value"],
        }
        freshness = self._freshness.for_snapshot(snapshot, queried_at=calculated_at)
        metrics = [
            self.metric_envelope(
                snapshot,
                source,
                key,
                overview[key],
                "currency" if key in {"revenue", "average_order_value"} else "count",
                period_start,
                period_end,
                overview["orders"],
                calculated_at=calculated_at,
                state="AVAILABLE" if overview["orders"] else "INSUFFICIENT_DATA",
            )
            for key in ("revenue", "orders", "customers", "average_order_value")
        ]
        return {
            **overview,
            "metrics": metrics,
            "data_freshness": freshness.as_dict(),
        }

    def sales_trend(
        self,
        snapshot,
        source: PreparedCompanyDataset,
        *,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        granularity: str = "month",
        product: str | None = None,
    ) -> dict[str, Any]:
        normalized = self.normalize_source_timezone(
            source, getattr(snapshot.company, "timezone", None) or "UTC"
        )
        result = compute_sales_trend(
            normalized,
            date_from=period_start,
            date_to=period_end,
            granularity=granularity,
            product=product,
        )
        freshness = self._freshness.for_snapshot(snapshot)
        return {**result, "data_freshness": freshness.as_dict()}

    def sales_comparison(
        self,
        snapshot,
        source: PreparedCompanyDataset,
        *,
        current_start: datetime,
        current_end: datetime,
        previous_start: datetime,
        previous_end: datetime,
    ) -> dict[str, Any]:
        current = self.sales_summary(
            snapshot, source, period_start=current_start, period_end=current_end
        )
        previous = self.sales_summary(
            snapshot, source, period_start=previous_start, period_end=previous_end
        )
        delta = round(float(current["revenue"]) - float(previous["revenue"]), 2)
        prior_revenue = float(previous["revenue"])
        change = round(delta / prior_revenue * 100, 2) if prior_revenue else None
        return {
            "current": current,
            "previous": previous,
            "absolute_change": delta,
            "change_percent": change,
            "currency": snapshot.currency,
            "data_freshness": current["data_freshness"],
        }

    def top_products(
        self,
        snapshot,
        source: PreparedCompanyDataset,
        *,
        top_n: int,
        metric: str,
        period_start: datetime | None,
        period_end: datetime | None,
        queried_at: datetime | None = None,
    ) -> dict[str, Any]:
        normalized = self.normalize_source_timezone(
            source, getattr(snapshot.company, "timezone", None) or "UTC"
        )
        result = compute_top_products(
            normalized,
            top_n=max(1, min(top_n, 50)),
            metric=metric,
            date_from=period_start,
            date_to=period_end,
        )
        calculated_at = self._utc(queried_at or datetime.now(timezone.utc))
        freshness = self._freshness.for_snapshot(snapshot, queried_at=calculated_at)
        source_ids = [str(source.dataset_id)]
        return {
            **result,
            "period_start": period_start,
            "period_end": period_end,
            "source_ids": source_ids,
            "source_type": snapshot.active_source_provider or snapshot.active_source_type or "dataset",
            "calculated_at": calculated_at,
            "freshness_status": freshness.freshness_status,
            "freshness_timestamp": freshness.last_updated_at,
            "data_freshness": freshness.as_dict(),
        }

    def customer_summary(
        self,
        snapshot,
        source: PreparedCompanyDataset,
        *,
        period_start: datetime | None,
        period_end: datetime | None,
        comparison_start: datetime | None = None,
        comparison_end: datetime | None = None,
        queried_at: datetime | None = None,
    ) -> dict[str, Any]:
        calculated_at = self._utc(queried_at or datetime.now(timezone.utc))
        normalized = self.normalize_source_timezone(
            source, getattr(snapshot.company, "timezone", None) or "UTC"
        )
        customers = compute_customer_portfolio(normalized)
        first_purchases = [
            (customer, self._utc(first_purchase))
            for customer in customers
            if (first_purchase := parse_business_datetime(customer.get("first_purchase"))) is not None
        ]
        previous_purchases = [
            customer
            for customer, first_purchase in first_purchases
            if comparison_start is not None
            and comparison_end is not None
            and self._utc(comparison_start) <= first_purchase <= self._utc(comparison_end)
        ]
        new_customers = [
            customer
            for customer, first_purchase in first_purchases
            if (period_start is None or first_purchase >= self._utc(period_start))
            and (period_end is None or first_purchase <= self._utc(period_end))
        ]
        dates = [
            self._utc(last_purchase)
            for customer in customers
            if (last_purchase := parse_business_datetime(customer.get("last_purchase"))) is not None
        ]
        active_cutoff = calculated_at - timedelta(days=90)
        active_customers = sum(1 for last_purchase in dates if last_purchase >= active_cutoff)
        total_customers = len(customers)
        repeat_customers = sum(1 for customer in customers if int(customer.get("orders") or 0) > 1)
        orders = compute_sales_summary(
            normalized, date_from=period_start, date_to=period_end, product=None
        )["orders"]
        average_frequency = round(
            sum(int(customer.get("orders") or 0) for customer in customers) / total_customers,
            2,
        ) if total_customers else 0.0
        summary = {
            "total_customers": total_customers,
            "new_customers": len(new_customers) if first_purchases else None,
            "previous_new_customers": len(previous_purchases) if first_purchases and comparison_start is not None else None,
            "active_customers": active_customers if dates else None,
            "repeat_customers": repeat_customers,
            "returning_customers": repeat_customers,
            "purchase_frequency": average_frequency,
            "average_customer_value": round(sum(float(customer.get("total_value") or 0) for customer in customers) / total_customers, 2) if total_customers else None,
        }
        freshness = self._freshness.for_snapshot(snapshot, queried_at=calculated_at)
        metrics = [
            self.metric_envelope(snapshot, source, metric_id, summary[metric_id], "count", period_start, period_end, orders, calculated_at=calculated_at, state="AVAILABLE" if summary[metric_id] is not None else "INSUFFICIENT_DATA")
            for metric_id in ("total_customers", "new_customers", "active_customers", "repeat_customers")
        ]
        return {**summary, "metrics": metrics, "data_freshness": freshness.as_dict()}

    def metric_envelope(
        self,
        snapshot,
        source: PreparedCompanyDataset | None,
        metric_id: str,
        value: float | int | None,
        unit: str,
        period_start: datetime | None,
        period_end: datetime | None,
        sample_size: int,
        *,
        calculated_at: datetime | None = None,
        state: str = "AVAILABLE",
    ) -> dict[str, Any]:
        calculated = self._utc(calculated_at or datetime.now(timezone.utc))
        freshness = self._freshness.for_snapshot(snapshot, queried_at=calculated)
        source_ids = (
            [str(item.dataset_id) for item in snapshot.prepared]
            if snapshot.active_source_type == "all"
            else [str(source.dataset_id)] if source is not None
            else [str(snapshot.active_source_dataset_id)] if snapshot.active_source_dataset_id is not None
            else []
        )
        return {
            "metric_id": metric_id,
            "value": value,
            "unit": unit,
            "currency": snapshot.currency if unit == "currency" else None,
            "period_start": period_start,
            "period_end": period_end,
            "source_ids": source_ids,
            "source_type": snapshot.active_source_provider or snapshot.active_source_type or "dataset",
            "calculated_at": calculated,
            "freshness_status": freshness.freshness_status,
            "freshness_timestamp": freshness.last_updated_at,
            "sample_size": sample_size,
            "availability_state": state,
        }

    @staticmethod
    def _timestamps(source, timezone_name: str) -> list[datetime]:
        if source is None:
            return []
        normalized = BusinessMetricsService.normalize_source_timezone(source, timezone_name)
        column = next((name for name, canonical in normalized.canonical_columns.items() if canonical == "order_timestamp"), None)
        if column is None:
            return []
        return [
            value.astimezone(timezone.utc)
            for row in normalized.rows
            if (value := parse_business_datetime(row.get(column))) is not None and value.tzinfo is not None
        ]

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    @staticmethod
    def _shift_month(value: datetime, month_delta: int) -> datetime:
        month_index = value.year * 12 + value.month - 1 + month_delta
        year, month_offset = divmod(month_index, 12)
        month = month_offset + 1
        return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))