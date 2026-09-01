"""Tenant-scoped Central AI orchestration over existing Avenqo services."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from backend.app.ai.central.routing import CentralAIIntentRouter
from backend.app.ai.chat.chat_service import ChatService
from backend.app.ai.usage.exceptions import AIQuotaExceededError
from backend.app.ai.usage.service import AIUsageService
from backend.app.assistants.registry import AssistantRegistry
from modules.entitlements import ModuleAccessDenied, ModuleAccessService
from shared.ai_engine.contracts import TenantContext


@dataclass(frozen=True, slots=True)
class CentralAIResult:
    selected_agent: str | None
    status: str
    answer: str | None
    remaining_ai_credits: int | None
    agent_availability: str


class CentralAIService:
    def __init__(
        self,
        registry: AssistantRegistry,
        chat_service: ChatService,
        usage_service: AIUsageService,
        module_access: ModuleAccessService,
    ) -> None:
        self._router = CentralAIIntentRouter(registry)
        self._chat = chat_service
        self._usage = usage_service
        self._module_access = module_access

    async def execute(
        self,
        tenant: TenantContext,
        user_id: UUID,
        conversation_id: UUID,
        query: str,
        *,
        permissions: frozenset[str],
        plan_code: str,
        capabilities: frozenset[str],
        request_id: str,
        user_language: str,
        company_country: str,
        company_currency: str,
        company_timezone: str,
    ) -> CentralAIResult:
        agent = self._router.select(query)
        if agent is None:
            return self._result(tenant.company_id, None, "unsupported_intent", plan_code, "unavailable")
        if not agent.status.is_executable:
            return self._result(tenant.company_id, agent.slug, "agent_unavailable", plan_code, agent.status.value)
        if agent.module_code is None:
            return self._result(tenant.company_id, agent.slug, "agent_unavailable", plan_code, "unavailable")
        try:
            self._module_access.require_active(tenant, agent.module_code)
        except ModuleAccessDenied:
            return self._result(tenant.company_id, agent.slug, "not_entitled", plan_code, "not_entitled")

        try:
            message, _ = await self._chat.send(
                tenant.company_id,
                user_id,
                conversation_id,
                query,
                permissions=permissions,
                plan_code=plan_code,
                capabilities=capabilities,
                request_id=request_id,
                user_language=user_language,
                company_country=company_country,
                company_currency=company_currency,
                company_timezone=company_timezone,
            )
        except AIQuotaExceededError:
            return self._result(tenant.company_id, agent.slug, "credits_exhausted", plan_code, "available")
        return self._result(tenant.company_id, agent.slug, "success", plan_code, "available", message.content)

    def _result(
        self,
        company_id: UUID,
        selected_agent: str | None,
        status: str,
        plan_code: str,
        availability: str,
        answer: str | None = None,
    ) -> CentralAIResult:
        balance = self._usage.get_credit_balance(company_id, plan_code)
        remaining = balance["total_remaining"]
        return CentralAIResult(selected_agent, status, answer, remaining, availability)
