"""Outils métier Avenqo : clients (Phase 30). READ-ONLY.

`get_customer_segments` consomme un modèle de segmentation déjà entraîné
(`PredictionService` + `resolve_active_model_type`) — aucun réentraînement
n'est jamais déclenché par une question de chat.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.base import RetailAITool, ToolArguments
from backend.app.ai.tools.business.dataset_access import load_latest_prepared_dataset
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.ai.tools.exceptions import ToolUnavailableError
from backend.app.services.company_dataset_ingestion_service import CompanyDatasetIngestionService
from backend.app.services.business_metrics_service import BusinessMetricsService
from backend.app.services.tenant_analytics_service import TenantAnalyticsService
from backend.app.services.portfolio_decision_service import (
    PortfolioAnalysisUnavailable,
    build_segmentation_signal,
)
from shared.ai_engine.prediction.service import PredictionService

RETAIL_MODULE_CODE = "retail"


class CustomerSummaryArgs(ToolArguments):
    period_key: str = "last_30_days"


class GetCustomerSummaryTool(RetailAITool):
    name = "get_customer_summary"
    description = "Return selected-source customer counts, including first-time customers in a company-local period. Supported period_key values include today, yesterday, this_week, last_week, this_month, last_month, year_to_date and all."
    input_schema = CustomerSummaryArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session, ingestion: CompanyDatasetIngestionService) -> None:
        self._session, self._ingestion = session, ingestion

    async def run(self, context: ToolExecutionContext, arguments: CustomerSummaryArgs) -> ToolResult:
        snapshot = TenantAnalyticsService(self._session, self._ingestion).load(context.tenant)
        prepared = load_latest_prepared_dataset(
            self._session,
            self._ingestion,
            context.tenant,
            frozenset({"customer_id", "order_id"}),
            snapshot=snapshot,
        )
        prepared = BusinessMetricsService.normalize_source_timezone(prepared, context.company_timezone)
        period = BusinessMetricsService.resolve_period(
            arguments.period_key,
            timezone_name=context.company_timezone,
            source=prepared,
        )
        data = BusinessMetricsService().customer_summary(
            snapshot,
            prepared,
            period_start=period["start"],
            period_end=period["end"],
            comparison_start=period["comparison_start"],
            comparison_end=period["comparison_end"],
        )
        return ToolResult(success=True, data=data, source_refs=(str(prepared.dataset_id),))


class CustomerSegmentsArgs(ToolArguments):
    pass


class GetCustomerSegmentsTool(RetailAITool):
    name = "get_customer_segments"
    description = (
        "Return the dominant customer segment identified by the tenant's already "
        "trained segmentation model, and its share of the customer portfolio."
    )
    input_schema = CustomerSegmentsArgs
    required_permissions = ("ai:use",)
    requires_capability = "segmentation"

    def __init__(self, session: Session, prediction_service: PredictionService) -> None:
        self._session, self._prediction_service = session, prediction_service

    async def run(self, context: ToolExecutionContext, arguments: CustomerSegmentsArgs) -> ToolResult:
        try:
            signal = build_segmentation_signal(
                self._session, context.tenant, RETAIL_MODULE_CODE, self._prediction_service
            )
        except PortfolioAnalysisUnavailable as exc:
            raise ToolUnavailableError(str(exc)) from exc

        return ToolResult(
            success=True,
            data={
                "dominant_segment": signal.entity,
                "segment_share": signal.value,
                "metric": signal.metric,
            },
            metadata={"model_capability": "segmentation"},
        )
