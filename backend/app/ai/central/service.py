"""Tenant-scoped Central AI orchestration over existing Avenqo services."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from time import perf_counter
from uuid import UUID

from backend.app.ai.central.context import CentralAIContextBuilder
from backend.app.ai.central.routing import CentralAIIntentRouter
from backend.app.ai.chat.chat_service import ChatService
from backend.app.ai.usage.exceptions import AIQuotaExceededError
from backend.app.ai.usage.service import AIUsageService
from backend.app.assistants.registry import AssistantRegistry
from shared.ai_engine.contracts import TenantContext

logger = logging.getLogger("avenqo.ai.central")


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
        context_builder: CentralAIContextBuilder,
    ) -> None:
        self._router = CentralAIIntentRouter(registry)
        self._chat = chat_service
        self._usage = usage_service
        self._context_builder = context_builder

    async def execute(
        self,
        tenant: TenantContext,
        user_id: UUID,
        conversation_id: UUID,
        query: str,
        *,
        permissions: frozenset[str],
        capabilities: frozenset[str],
        request_id: str,
        user_language: str,
        company_country: str,
        company_currency: str,
        company_timezone: str,
        page_context: str | None = None,
    ) -> CentralAIResult:
        started_at = perf_counter()
        self._chat.validate_conversation(tenant.company_id, user_id, conversation_id)
        context = self._context_builder.build(
            tenant,
            user_id,
            permissions=permissions,
            user_language=user_language,
            company_country=company_country,
            company_currency=company_currency,
            company_timezone=company_timezone,
        )
        if "ai:use" not in permissions:
            result = self._result(
                tenant.company_id,
                None,
                "not_authorized",
                context.plan_code,
                "unavailable",
            )
            self._log_result(tenant.company_id, None, result, started_at, "permission_denied")
            return result
        agent = self._router.select(query)
        if agent is None:
            try:
                self._usage.ensure_quota_available(tenant.company_id, context.plan_code)
            except AIQuotaExceededError:
                result = self._result(
                    tenant.company_id,
                    None,
                    "credits_exhausted",
                    context.plan_code,
                    "available",
                )
                self._log_result(tenant.company_id, None, result, started_at, "free_form_classification")
                return result
            agent = await self._router.select_free_form(query, self._chat.classify_intent)
        if agent is not None and not agent.status.is_executable:
            result = self._result(tenant.company_id, agent.slug, "agent_unavailable", context.plan_code, agent.status.value)
            self._log_result(tenant.company_id, agent.module_code, result, started_at, "module_unavailable")
            return result
        if agent is not None and (agent.module_code is None or agent.module_code not in context.active_modules):
            result = self._result(tenant.company_id, agent.slug, "not_entitled", context.plan_code, "not_entitled")
            self._log_result(tenant.company_id, agent.module_code, result, started_at, "module_inactive")
            return result

        try:
            message, _ = await self._chat.send(
                tenant.company_id,
                user_id,
                conversation_id,
                query,
                permissions=permissions,
                plan_code=context.plan_code,
                capabilities=capabilities,
                request_id=request_id,
                user_language=user_language,
                company_country=company_country,
                company_currency=company_currency,
                company_timezone=company_timezone,
                trusted_context=context.as_prompt_context(),
                client_context=page_context or "",
                allowed_tool_names=agent.allowed_tool_names if agent is not None else frozenset(),
                retrieve_tenant_data=agent is not None,
            )
        except AIQuotaExceededError:
            result = self._result(tenant.company_id, agent.slug if agent else None, "credits_exhausted", context.plan_code, "available")
        else:
            result = self._result(tenant.company_id, agent.slug if agent else None, "success", context.plan_code, "available", message.content)
        self._log_result(
            tenant.company_id,
            agent.module_code if agent else None,
            result,
            started_at,
            "deterministic_module" if agent else "general_fallback",
        )
        return result

    def _log_result(
        self,
        company_id: UUID,
        module_code: str | None,
        result: CentralAIResult,
        started_at: float,
        route: str,
    ) -> None:
        logger.info(
            "central_ai_request tenant_id=%s selected_module=%s provider=%s credit_cost=%d status=%s latency_ms=%d route=%s",
            company_id,
            module_code,
            self._chat.provider_name,
            1 if result.status == "success" else 0,
            result.status,
            int((perf_counter() - started_at) * 1000),
            route,
        )

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
