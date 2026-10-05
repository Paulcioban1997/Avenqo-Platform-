"""Tenant-scoped Central AI orchestration over existing Avenqo services."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from time import perf_counter
from uuid import UUID

from backend.app.ai.request_timeout import bounded_ai_request
from backend.app.ai.central.context import CentralAIContextBuilder
from backend.app.ai.central.routing import CentralAIIntentRouter
from backend.app.ai.chat.chat_service import ChatService
from backend.app.ai.usage.exceptions import AIQuotaExceededError
from backend.app.ai.llm.schemas import LLMProviderAttempt
from backend.app.ai.usage.service import AIUsageService
from backend.app.core.locale_catalog import detect_spoken_language, resolve_locale
from backend.app.core.error_localization import agent_upgrade_message
from backend.app.assistants.registry import AssistantRegistry, agent_entitlements
from shared.ai_engine.contracts import TenantContext

logger = logging.getLogger("avenqo.ai.central")


@dataclass(frozen=True, slots=True)
class CentralAIResult:
    selected_agent: str | None
    status: str
    answer: str | None
    remaining_ai_credits: int | None
    agent_availability: str
    tool_outcomes: tuple[dict[str, object], ...] = ()


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

    @property
    def usage_service(self) -> AIUsageService:
        return self._usage

    def capability_context(self, tenant: TenantContext, user_id: UUID, **kwargs):
        return self._context_builder.build(tenant, user_id, **kwargs)

    def _tool_scope_for_request(
        self,
        agent,
        query: str,
        page_context: str | None,
        active_modules: frozenset[str],
    ) -> tuple[frozenset[str], dict[str, str]] | None:
        if agent is None:
            return frozenset(), {}
        if not agent.aggregate:
            if not agent_entitlements(agent).issubset(active_modules):
                return None
            tool_agents = {name: agent.agent_id for name in agent.allowed_tool_names}
            return agent.allowed_tool_names, tool_agents

        requested_agents = self._router.select_matching_agents(
            query,
            page_context=page_context,
        )
        tool_agents: dict[str, str] = {}
        for requested_agent in requested_agents:
            if not agent_entitlements(requested_agent).issubset(active_modules):
                return None
            for tool_name in requested_agent.allowed_tool_names:
                tool_agents[tool_name] = requested_agent.agent_id

        if agent_entitlements(agent).issubset(active_modules):
            for tool_name in agent.allowed_tool_names:
                tool_agents[tool_name] = agent.agent_id
        elif not requested_agents:
            return None

        return frozenset(tool_agents), tool_agents

    @bounded_ai_request
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
        locale_explicit: bool = True,
        allow_existing_reservation: bool = False,
        attempt_sink: list[LLMProviderAttempt] | None = None,
        spoken_language_input: bool = False,
    ) -> CentralAIResult:
        user_language = resolve_locale(user_language)
        language_source = "explicit" if locale_explicit else "fallback"
        language_confidence = None
        language_explicitly_requested = False
        language_auto_detect = False
        if spoken_language_input or not locale_explicit:
            language_detection = detect_spoken_language(
                query, preferred_locale=user_language
            )
            language_source = language_detection.source
            language_confidence = language_detection.confidence
            language_explicitly_requested = language_detection.source == "explicit_request"
            if language_detection.locale is not None:
                user_language = language_detection.locale
                locale_explicit = True
            elif spoken_language_input:
                language_auto_detect = True
        started_at = perf_counter()
        self._chat.validate_conversation(tenant.company_id, user_id, conversation_id)
        tenant = type(tenant)(company_id=tenant.company_id, user_id=user_id)
        context = self._context_builder.build(
            tenant,
            user_id,
            permissions=permissions,
            user_language=user_language,
            company_country=company_country,
            company_currency=company_currency,
            company_timezone=company_timezone,
            language_source=language_source,
            language_confidence=language_confidence,
            language_auto_detect=language_auto_detect,
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
        agent = self._router.select(query, page_context=page_context)
        if agent is None:
            try:
                if not allow_existing_reservation:
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

            async def classify(system_instruction: str, prompt: str) -> str:
                classification_request_id = (
                    request_id if allow_existing_reservation else f"{request_id}:classification"
                )
                return await self._chat.classify_intent(
                    system_instruction,
                    prompt,
                    tenant_id=tenant.company_id,
                    plan_code=context.plan_code,
                    request_id=classification_request_id,
                    allow_existing_reservation=allow_existing_reservation,
                    attempt_sink=attempt_sink,
                )

            agent = await self._router.select_free_form(query, classify)
        if agent is not None and not agent.status.is_executable:
            result = self._result(tenant.company_id, agent.slug, "agent_unavailable", context.plan_code, agent.status.value)
            self._log_result(tenant.company_id, agent.module_code, result, started_at, "module_unavailable")
            return result
        scoped_agents = (agent, *self._router.select_matching_agents(query, page_context=page_context)) if agent is not None and agent.aggregate else (agent,)
        if any(item is not None and not item.required_permissions.issubset(permissions) for item in scoped_agents):
            result = self._result(tenant.company_id, agent.slug, "not_authorized", context.plan_code, "unavailable")
            self._log_result(tenant.company_id, agent.module_code, result, started_at, "agent_permission_denied")
            return result
        tool_scope = self._tool_scope_for_request(
            agent,
            query,
            page_context,
            frozenset(context.active_modules),
        )
        if tool_scope is None:
            result = self._result(
                tenant.company_id, agent.slug, "not_entitled", context.plan_code, "not_entitled",
                answer=agent_upgrade_message(user_language),
            )
            self._log_result(tenant.company_id, agent.module_code, result, started_at, "module_inactive")
            return result
        allowed_tool_names, authorized_tool_agents = tool_scope

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
                allowed_tool_names=allowed_tool_names,
                selected_agent_id=agent.agent_id if agent is not None else None,
                module_id=agent.module_code if agent is not None else None,
                locale_explicit=locale_explicit,
                authorized_tool_agents=authorized_tool_agents,
                retrieve_tenant_data=agent is not None and agent.slug not in {"tenant_capabilities", "voice"},
                allow_existing_reservation=allow_existing_reservation,
                attempt_sink=attempt_sink,
                follow_latest_utterance_language=spoken_language_input,
                language_explicitly_requested=language_explicitly_requested,
                language_auto_detect=language_auto_detect,
            )
        except AIQuotaExceededError:
            result = self._result(tenant.company_id, agent.slug if agent else None, "credits_exhausted", context.plan_code, "available")
        else:
            outcomes = self._safe_tool_outcomes(
                getattr(self._chat, "last_tool_call_results", ())
            )
            result = self._result(
                tenant.company_id,
                agent.slug if agent else None,
                "success",
                context.plan_code,
                "available",
                message.content,
                outcomes,
            )
        self._log_result(
            tenant.company_id,
            agent.module_code if agent else None,
            result,
            started_at,
            "deterministic_module" if agent else "general_fallback",
        )
        return result

    @staticmethod
    def _safe_tool_outcomes(tool_call_results) -> tuple[dict[str, object], ...]:
        outcomes = []
        for call_result in tool_call_results:
            tool_name = call_result.call.name
            tool_result = call_result.result
            confirmed = bool(tool_result.success)
            if tool_name == "check_availability":
                confirmed = confirmed and tool_result.data.get("state") == "AVAILABLE"
            elif tool_name == "create_appointment":
                confirmed = (
                    confirmed
                    and bool(tool_result.data.get("id"))
                    and tool_result.data.get("calendar_synced") is True
                )
            elif tool_name == "list_available_slots":
                confirmed = confirmed and isinstance(tool_result.data.get("slots"), list)
            outcomes.append({"tool": tool_name, "success": bool(tool_result.success), "confirmed": confirmed})
        return tuple(outcomes)

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
        tool_outcomes: tuple[dict[str, object], ...] = (),
    ) -> CentralAIResult:
        balance = self._usage.get_credit_balance(company_id, plan_code)
        remaining = balance["total_remaining"]
        return CentralAIResult(selected_agent, status, answer, remaining, availability, tool_outcomes)
