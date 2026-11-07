"""Platform, Marketplace & Billing AI tools for Central AI orchestration (Phase 8.1).

Enables Central AI to inspect real connector statuses (Shopify, WooCommerce),
and report accurate AI credit balances and plan limits.
"""

from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import MarketplaceAITool, BillingCreditsAITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.models.commerce_connection import CommerceConnection
from backend.app.models.company import Company
from backend.app.ai.usage.service import AIUsageService
from backend.app.ai.usage.policy import AIQuotaPolicy
from backend.app.config.settings import get_settings


class EmptyArgs(ToolArguments):
    pass


class GetCommerceConnectionsStatusTool(MarketplaceAITool):
    name = "get_commerce_connections_status"
    description = (
        "Consulte l'état réel des connecteurs e-commerce de l'entreprise (Shopify, WooCommerce, etc.) : "
        "statut de synchronisation, connecteurs actifs, nombre d'enregistrements traités."
    )
    input_schema = EmptyArgs
    required_permissions = ("ai:use", "data:read")

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: EmptyArgs) -> ToolResult:
        conns = list(
            self._session.scalars(
                select(CommerceConnection).where(
                    CommerceConnection.company_id == context.tenant.company_id
                )
            ).all()
        )

        results = [
            {
                "id": str(c.id),
                "provider": c.provider,
                "display_name": c.display_name or c.provider,
                "status": c.status,
                "records_processed": c.records_processed,
                "records_created": c.records_created,
                "last_sync_error": c.sync_error_message,
            }
            for c in conns
        ]

        return ToolResult(
            success=True,
            data={
                "connections_count": len(results),
                "connections": results,
            },
            source_refs=("commerce_connections",),
        )


class GetAICreditsBalanceTool(BillingCreditsAITool):
    name = "get_ai_credits_balance"
    description = (
        "Consulte le solde réel de crédits IA de l'entreprise, le plan d'abonnement actif "
        "et les plafonds de consommation mensuels."
    )
    input_schema = EmptyArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: EmptyArgs) -> ToolResult:
        company = self._session.scalar(select(Company).where(Company.id == context.tenant.company_id))
        plan_code = company.subscription_plan if company else "professional"

        settings = get_settings()
        usage_service = AIUsageService(
            self._session,
            AIQuotaPolicy(settings),
            settings.avenqo_provider_cost_per_credit_usd,
            settings.ai_credit_reservation_ttl_minutes,
        )

        balance = usage_service.get_credit_balance(context.tenant.company_id, plan_code)
        status_str = getattr(company.status, "value", str(company.status)).lower() if company else "unknown"

        return ToolResult(
            success=True,
            data={
                "company_id": str(context.tenant.company_id),
                "plan_code": plan_code,
                "credit_balance": balance,
                "status": "active" if status_str == "active" else "restricted",
            },
            source_refs=("tenant_ai_credit_balances", "companies"),
        )
