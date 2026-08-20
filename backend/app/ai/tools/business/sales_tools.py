"""Outils métier Avenqo : ventes (Phase 30). READ-ONLY.

Chaque outil s'appuie sur `PreparedCompanyDataset` (Phase 26/27) — jamais un
accès SQL brut, jamais une donnée fictive.
"""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.business.analytics import (
    TOP_PRODUCTS_METRICS,
    compute_business_overview,
    compute_sales_comparison,
    compute_sales_summary,
    compute_sales_trend,
    compute_top_products,
)
from backend.app.ai.tools.business.dataset_access import load_latest_prepared_dataset
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService


def _to_datetime(value: date | None, *, end_of_day: bool) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, time.max if end_of_day else time.min)


class BusinessOverviewArgs(ToolArguments):
    pass


class GetBusinessOverviewTool(AITool):
    name = "get_business_overview"
    description = (
        "Return a synthetic view of the company's business performance: revenue, "
        "orders, customers and average order value, computed from the tenant's "
        "own connected business data."
    )
    input_schema = BusinessOverviewArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session, ingestion: CompanyDatasetIngestionService) -> None:
        self._session, self._ingestion = session, ingestion

    async def run(self, context: ToolExecutionContext, arguments: BusinessOverviewArgs) -> ToolResult:
        prepared = load_latest_prepared_dataset(self._session, self._ingestion, context.tenant)
        data = compute_business_overview(prepared)
        return ToolResult(success=True, data=data, source_refs=(str(prepared.dataset_id),))


class SalesSummaryArgs(ToolArguments):
    date_from: date | None = None
    date_to: date | None = None
    location: str | None = None
    category: str | None = None
    product: str | None = None


class GetSalesSummaryTool(AITool):
    name = "get_sales_summary"
    description = (
        "Return the sales revenue, order count and average order value for the "
        "tenant's business data, optionally filtered by date range or product. "
        "Use date_from/date_to as real calendar dates, never free text."
    )
    input_schema = SalesSummaryArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session, ingestion: CompanyDatasetIngestionService) -> None:
        self._session, self._ingestion = session, ingestion

    async def run(self, context: ToolExecutionContext, arguments: SalesSummaryArgs) -> ToolResult:
        prepared = load_latest_prepared_dataset(self._session, self._ingestion, context.tenant)
        data = compute_sales_summary(
            prepared,
            date_from=_to_datetime(arguments.date_from, end_of_day=False),
            date_to=_to_datetime(arguments.date_to, end_of_day=True),
            product=arguments.product,
        )
        unsupported = [name for name, value in (("location", arguments.location), ("category", arguments.category)) if value is not None]
        metadata = {"unsupported_filters": unsupported} if unsupported else {}
        return ToolResult(success=True, data=data, source_refs=(str(prepared.dataset_id),), metadata=metadata)


class SalesTrendArgs(ToolArguments):
    pass


class GetSalesTrendTool(AITool):
    name = "get_sales_trend"
    description = "Return the monthly revenue trend as a structured time series for the tenant's business data."
    input_schema = SalesTrendArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session, ingestion: CompanyDatasetIngestionService) -> None:
        self._session, self._ingestion = session, ingestion

    async def run(self, context: ToolExecutionContext, arguments: SalesTrendArgs) -> ToolResult:
        prepared = load_latest_prepared_dataset(self._session, self._ingestion, context.tenant)
        data = compute_sales_trend(prepared)
        return ToolResult(success=True, data=data, source_refs=(str(prepared.dataset_id),))


class SalesComparisonArgs(ToolArguments):
    current_from: date
    current_to: date
    previous_from: date
    previous_to: date


class GetSalesComparisonTool(AITool):
    name = "get_sales_comparison"
    description = (
        "Compare revenue between two real date ranges (e.g. this month vs previous "
        "month) and return the absolute and percentage change."
    )
    input_schema = SalesComparisonArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session, ingestion: CompanyDatasetIngestionService) -> None:
        self._session, self._ingestion = session, ingestion

    async def run(self, context: ToolExecutionContext, arguments: SalesComparisonArgs) -> ToolResult:
        prepared = load_latest_prepared_dataset(self._session, self._ingestion, context.tenant)
        data = compute_sales_comparison(
            prepared,
            current_from=_to_datetime(arguments.current_from, end_of_day=False),
            current_to=_to_datetime(arguments.current_to, end_of_day=True),
            previous_from=_to_datetime(arguments.previous_from, end_of_day=False),
            previous_to=_to_datetime(arguments.previous_to, end_of_day=True),
        )
        return ToolResult(success=True, data=data, source_refs=(str(prepared.dataset_id),))


class TopProductsArgs(ToolArguments):
    top_n: int = 5
    metric: str = "revenue"
    date_from: date | None = None
    date_to: date | None = None
    category: str | None = None


class GetTopProductsTool(AITool):
    name = "get_top_products"
    description = (
        "Return the top-performing products for the tenant, ranked by revenue, "
        "quantity sold, or number of orders."
    )
    input_schema = TopProductsArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session, ingestion: CompanyDatasetIngestionService) -> None:
        self._session, self._ingestion = session, ingestion

    async def run(self, context: ToolExecutionContext, arguments: TopProductsArgs) -> ToolResult:
        if arguments.metric not in TOP_PRODUCTS_METRICS:
            return ToolResult(
                success=False,
                error=f"Unsupported metric '{arguments.metric}'. Allowed: {', '.join(TOP_PRODUCTS_METRICS)}.",
            )
        top_n = max(1, min(arguments.top_n, 50))
        prepared = load_latest_prepared_dataset(self._session, self._ingestion, context.tenant)
        data = compute_top_products(
            prepared,
            top_n=top_n,
            metric=arguments.metric,
            date_from=_to_datetime(arguments.date_from, end_of_day=False),
            date_to=_to_datetime(arguments.date_to, end_of_day=True),
        )
        metadata = {"unsupported_filters": ["category"]} if arguments.category is not None else {}
        return ToolResult(success=True, data=data, source_refs=(str(prepared.dataset_id),), metadata=metadata)
