"""Outils sûrs, en lecture seule, pour le Support AI Avenqo (Phase 32).

Aucun de ces outils ne peut renvoyer une donnée métier tenant (ventes,
clients, etc.) : uniquement de la documentation produit, le plan/les
capacités du tenant courant, et un statut générique de connexion/santé IA.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.llm.health import ProviderHealthRegistry, ProviderHealthStatus
from backend.app.ai.support.retrieval_service import PlatformKnowledgeRetrievalService
from backend.app.ai.tools.base import AITool, ToolArguments
from backend.app.ai.tools.business.registry_factory import resolve_tenant_capabilities
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.ai.usage.policy import MONTHLY_AI_REQUESTS
from backend.app.ai.usage.service import AIUsageService
from backend.app.models import BillingAccount, Company, Dataset
from pydantic import Field
from shared.ai_engine.prediction.service import PredictionService


class SearchAvenqoDocsArgs(ToolArguments):
    query: str = Field(min_length=1, max_length=300)


class SearchAvenqoDocsTool(AITool):
    name = "search_avenqo_docs"
    description = "Search Avenqo's product documentation (how-to guides, FAQ, troubleshooting). Never returns business data."
    input_schema = SearchAvenqoDocsArgs

    def __init__(self, retrieval: PlatformKnowledgeRetrievalService) -> None:
        self._retrieval = retrieval

    async def run(self, context: ToolExecutionContext, arguments: SearchAvenqoDocsArgs) -> ToolResult:
        sources = self._retrieval.retrieve_context(arguments.query)
        if not sources:
            return ToolResult(success=True, data={"results": []})
        return ToolResult(
            success=True,
            data={"results": [{"title": source.name, "content": source.content} for source in sources]},
            source_refs=tuple(source.identifier for source in sources),
        )


class GetCurrentPlanTool(AITool):
    name = "get_current_plan"
    description = "Get the current company's subscription plan. Never reveals pricing or data for other companies."

    def __init__(self, db: Session) -> None:
        self._db = db

    async def run(self, context: ToolExecutionContext, arguments: ToolArguments) -> ToolResult:
        company = self._db.scalar(select(Company).where(Company.id == context.tenant_id))
        if company is None:
            return ToolResult(success=False, error="Company not found")
        return ToolResult(success=True, data={"plan_code": company.subscription_plan})


class GetAvailableFeaturesTool(AITool):
    name = "get_available_features"
    description = "Get the list of AI/module capabilities currently enabled for the company. Never reveals business data."

    def __init__(self, db: Session, prediction_service: PredictionService) -> None:
        self._db = db
        self._prediction_service = prediction_service

    async def run(self, context: ToolExecutionContext, arguments: ToolArguments) -> ToolResult:
        capabilities = resolve_tenant_capabilities(self._db, context.tenant, self._prediction_service)
        return ToolResult(success=True, data={"capabilities": sorted(capabilities)})


class GetConnectionStatusTool(AITool):
    name = "get_connection_status"
    description = "Check whether the company has at least one connected data source. Never reveals the data itself."

    def __init__(self, db: Session) -> None:
        self._db = db

    async def run(self, context: ToolExecutionContext, arguments: ToolArguments) -> ToolResult:
        count = self._db.scalar(select(Dataset).where(Dataset.company_id == context.tenant_id).limit(1))
        return ToolResult(success=True, data={"has_connected_data_source": count is not None})


class GetAICapabilityStatusTool(AITool):
    name = "get_ai_capability_status"
    description = "Get a generic status of Avenqo's AI availability (healthy/degraded/unavailable). Never reveals which provider is used."

    def __init__(self, health_registry: ProviderHealthRegistry) -> None:
        self._health_registry = health_registry

    async def run(self, context: ToolExecutionContext, arguments: ToolArguments) -> ToolResult:
        statuses = set(self._health_registry.snapshot().values())
        if not statuses or statuses == {ProviderHealthStatus.HEALTHY.value}:
            aggregate = "healthy"
        elif ProviderHealthStatus.UNAVAILABLE.value in statuses and len(statuses) == 1:
            aggregate = "unavailable"
        else:
            aggregate = "degraded"
        return ToolResult(success=True, data={"status": aggregate})


class GetBillingStatusTool(AITool):
    name = "get_billing_status"
    description = (
        "Get the current company's subscription status, billing period, and whether the "
        "monthly AI usage limit has been reached. Never reveals prices, invoices content, or other companies' data."
    )

    def __init__(self, db: Session, usage_service: AIUsageService) -> None:
        self._db = db
        self._usage_service = usage_service

    async def run(self, context: ToolExecutionContext, arguments: ToolArguments) -> ToolResult:
        company = self._db.scalar(select(Company).where(Company.id == context.tenant_id))
        if company is None:
            return ToolResult(success=False, error="Company not found")
        account = self._db.scalar(select(BillingAccount).where(BillingAccount.company_id == company.id))
        usage = self._usage_service.get_usage(company.id, company.subscription_plan)
        limit = self._usage_service.limit_for(company.id, company.subscription_plan, MONTHLY_AI_REQUESTS)
        quota_reached = limit is not None and usage.ai_requests_count >= limit
        return ToolResult(
            success=True,
            data={
                "plan_code": company.subscription_plan,
                "subscription_status": account.status if account else "inactive",
                "cancel_at_period_end": account.cancel_at_period_end if account else False,
                "monthly_ai_quota_reached": quota_reached,
            },
        )
