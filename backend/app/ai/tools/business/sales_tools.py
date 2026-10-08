"""Outils métier Avenqo : ventes (Phase 30). READ-ONLY.

Chaque outil s'appuie sur `PreparedCompanyDataset` (Phase 26/27) — jamais un
accès SQL brut, jamais une donnée fictive.
"""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.base import RetailAITool, ToolArguments
from backend.app.ai.tools.business.analytics import (
    TOP_PRODUCTS_METRICS,
    compute_business_overview,
    compute_sales_comparison,
    compute_sales_summary,
    compute_sales_trend,
)
from backend.app.ai.tools.business.dataset_access import load_latest_prepared_dataset
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.models import Company
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from backend.app.services.business_metrics_service import BusinessMetricsService
from backend.app.services.tenant_analytics_service import TenantAnalyticsService


def _to_datetime(value: date | None, *, end_of_day: bool) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, time.max if end_of_day else time.min)


def _with_currency(session: Session, context: ToolExecutionContext, data: dict[str, object]) -> dict[str, object]:
    """Ajoute `currency_code` (ISO-4217 de l'entreprise) aux valeurs monétaires.

    Valeur numérique brute + code devise — JAMAIS de symbole concaténé ("€284"),
    jamais de conversion FX inventée. Le LLM formate selon locale + currency.
    """

    currency = getattr(context, "currency_code", None)
    if not currency:
        company = session.get(Company, context.tenant.company_id)
        currency = getattr(company, "currency_code", None) or "USD"
    return {**data, "currency_code": currency}


class BusinessOverviewArgs(ToolArguments):
    pass


class GetBusinessOverviewTool(RetailAITool):
    name = "get_business_overview"
    description = (
        "Return a synthetic view of the company's business performance: revenue, "
        "orders, customers and average order value, computed from the tenant's "
        "own connected business data."
    )
    input_schema = BusinessOverviewArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session, ingestion: CompanyDatasetIngestionService) -> None:
        self._session, self._ingestion = session, ingestion

    async def run(self, context: ToolExecutionContext, arguments: BusinessOverviewArgs) -> ToolResult:
        snapshot = TenantAnalyticsService(self._session, self._ingestion).load(context.tenant)
        prepared = load_latest_prepared_dataset(
            self._session,
            self._ingestion,
            context.tenant,
            frozenset({"total_amount", "order_id", "customer_id"}),
            snapshot=snapshot,
        )
        data = BusinessMetricsService().business_overview(snapshot, prepared)
        return ToolResult(success=True, data=_with_currency(self._session, context, data), source_refs=(str(prepared.dataset_id),))


class SalesSummaryArgs(ToolArguments):
    date_from: date | None = None
    date_to: date | None = None
    period_key: str | None = None
    location: str | None = None
    category: str | None = None
    product: str | None = None


class GetSalesSummaryTool(RetailAITool):
    name = "get_sales_summary"
    description = (
        "Return the sales revenue, order count and average order value for the "
        "tenant's business data, optionally filtered by date range or product. "
        "Use period_key for today, yesterday, this_week, last_week, last_7_days, last_30_days, "
        "current_month, last_month, current_quarter, last_quarter or year_to_date. "
        "The server interprets these in the company's timezone. Use date_from/date_to for a custom range."
    )
    input_schema = SalesSummaryArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session, ingestion: CompanyDatasetIngestionService) -> None:
        self._session, self._ingestion = session, ingestion

    async def run(self, context: ToolExecutionContext, arguments: SalesSummaryArgs) -> ToolResult:
        snapshot = TenantAnalyticsService(self._session, self._ingestion).load(context.tenant)
        prepared = load_latest_prepared_dataset(
            self._session,
            self._ingestion,
            context.tenant,
            frozenset({"total_amount", "order_id"}),
            snapshot=snapshot,
        )
        metrics_service = BusinessMetricsService()
        period_key = (
            "custom"
            if arguments.date_from is not None or arguments.date_to is not None
            else arguments.period_key or "all"
        )
        bounds = metrics_service.resolve_period(
            period_key,
            timezone_name=context.company_timezone,
            date_from=arguments.date_from,
            date_to=arguments.date_to,
            source=prepared,
        )
        data = metrics_service.sales_summary(
            snapshot,
            prepared,
            period_start=bounds["start"],
            period_end=bounds["end"],
            product=arguments.product,
        )
        unsupported = [name for name, value in (("location", arguments.location), ("category", arguments.category)) if value is not None]
        metadata: dict[str, Any] = {"unsupported_filters": unsupported} if unsupported else {}
        if not data.get("data_covered", True):
            metadata["data_covered"] = False
            metadata["warning"] = data.get("coverage_message")
        return ToolResult(success=True, data=_with_currency(self._session, context, data), source_refs=(str(prepared.dataset_id),), metadata=metadata)


class SalesTrendArgs(ToolArguments):
    period_key: str | None = None
    granularity: str = "month"
    product: str | None = None


class GetSalesTrendTool(RetailAITool):
    name = "get_sales_trend"
    description = "Return a structured sales trend for the selected tenant source and company-local period."
    input_schema = SalesTrendArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session, ingestion: CompanyDatasetIngestionService) -> None:
        self._session, self._ingestion = session, ingestion

    async def run(self, context: ToolExecutionContext, arguments: SalesTrendArgs) -> ToolResult:
        snapshot = TenantAnalyticsService(self._session, self._ingestion).load(context.tenant)
        prepared = load_latest_prepared_dataset(
            self._session,
            self._ingestion,
            context.tenant,
            frozenset({"total_amount", "order_timestamp"}),
            snapshot=snapshot,
        )
        metrics_service = BusinessMetricsService()
        bounds = metrics_service.resolve_period(
            arguments.period_key or "all",
            timezone_name=context.company_timezone,
            source=prepared,
        )
        granularity = arguments.granularity if arguments.granularity in {"day", "week", "month"} else "month"
        data = metrics_service.sales_trend(
            snapshot,
            prepared,
            period_start=bounds["start"],
            period_end=bounds["end"],
            granularity=granularity,
            product=arguments.product,
        )
        return ToolResult(success=True, data=_with_currency(self._session, context, data), source_refs=(str(prepared.dataset_id),))


class SalesComparisonArgs(ToolArguments):
    current_from: date
    current_to: date
    previous_from: date
    previous_to: date


class GetSalesComparisonTool(RetailAITool):
    name = "get_sales_comparison"
    description = (
        "Compare revenue between two real date ranges (e.g. this month vs previous "
        "month) and return the absolute and percentage change."
    )
    input_schema = SalesComparisonArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session, ingestion: CompanyDatasetIngestionService) -> None:
        self._session, self._ingestion = session, ingestion

    async def run(self, context: ToolExecutionContext, arguments: SalesComparisonArgs) -> ToolResult:
        snapshot = TenantAnalyticsService(self._session, self._ingestion).load(context.tenant)
        prepared = load_latest_prepared_dataset(
            self._session,
            self._ingestion,
            context.tenant,
            frozenset({"total_amount", "order_timestamp"}),
            snapshot=snapshot,
        )
        metrics_service = BusinessMetricsService()
        current_bounds = metrics_service.resolve_period(
            "custom",
            timezone_name=context.company_timezone,
            date_from=arguments.current_from,
            date_to=arguments.current_to,
        )
        previous_bounds = metrics_service.resolve_period(
            "custom",
            timezone_name=context.company_timezone,
            date_from=arguments.previous_from,
            date_to=arguments.previous_to,
        )
        data = metrics_service.sales_comparison(
            snapshot,
            prepared,
            current_start=current_bounds["start"],
            current_end=current_bounds["end"],
            previous_start=previous_bounds["start"],
            previous_end=previous_bounds["end"],
        )
        return ToolResult(success=True, data=data, source_refs=(str(prepared.dataset_id),))


class TopProductsArgs(ToolArguments):
    top_n: int = 5
    metric: str = "revenue"
    date_from: date | None = None
    date_to: date | None = None
    period_key: str | None = None
    category: str | None = None


class GetTopProductsTool(RetailAITool):
    name = "get_top_products"
    description = (
        "Return the top-performing products for the tenant, ranked by revenue, "
        "quantity sold, or number of orders."
    )
    input_schema = TopProductsArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session, ingestion: CompanyDatasetIngestionService) -> None:
        self._session, self._ingestion = session, ingestion

    async def run(self, context: ToolExecutionContext, arguments: TopProductsArgs) -> ToolResult:
        if arguments.metric not in TOP_PRODUCTS_METRICS:
            return ToolResult(
                success=False,
                error=f"Unsupported metric '{arguments.metric}'. Allowed: {', '.join(TOP_PRODUCTS_METRICS)}.",
            )
        top_n = max(1, min(arguments.top_n, 50))
        metric_field = {
            "revenue": "total_amount",
            "quantity": "quantity",
            "orders": "order_id",
        }[arguments.metric]
        snapshot = TenantAnalyticsService(self._session, self._ingestion).load(context.tenant)
        prepared = load_latest_prepared_dataset(
            self._session,
            self._ingestion,
            context.tenant,
            frozenset({"product_id", metric_field}),
            snapshot=snapshot,
        )
        metrics_service = BusinessMetricsService()
        period_key = (
            "custom"
            if arguments.date_from is not None or arguments.date_to is not None
            else arguments.period_key or "all"
        )
        bounds = metrics_service.resolve_period(
            period_key,
            timezone_name=context.company_timezone,
            date_from=arguments.date_from,
            date_to=arguments.date_to,
            source=prepared,
        )
        data = metrics_service.top_products(
            snapshot,
            prepared,
            top_n=top_n,
            metric=arguments.metric,
            period_start=bounds["start"],
            period_end=bounds["end"],
        )
        metadata = {"unsupported_filters": ["category"]} if arguments.category is not None else {}
        return ToolResult(success=True, data=data, source_refs=(str(prepared.dataset_id),), metadata=metadata)
