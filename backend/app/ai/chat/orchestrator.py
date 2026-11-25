"""Boucle d'orchestration Tool Calling contrôlée (Phase 30, section 17) et honnêteté de grounding.

Jamais de boucle infinie : `MAX_TOOL_ITERATIONS` et `MAX_TOOLS_PER_REQUEST`
bornent strictement le nombre d'aller-retours LLM ↔ outils pour une seule
question utilisateur.

Garanties additionnelles Phase C / H (OCR, Excel & Central AI Grounding) :
- Relecture automatique du document source complet (`extract_invoice_totals` / `get_document_source`)
  si seul un aperçu tronqué (`search_documents` ou `truncated=True`) a été consulté sur une
  question financière/documentaire avant que le modèle ne conclue à l'absence d'un montant.
- Classification stricte et honnête du grounding (`source_accessible`, `extracted_structured`,
  `math_verified`, `uncertain_candidates`, `missing_after_full_read`, `preview_only`, `ungrounded`) :
  ne marque JAMAIS `certified_grounding=True` lorsqu'un aperçu tronqué ou incertain a seul été lu.
- Neutralisation de tout artefact brut `***` dans les résumés d'outils et réponses finales.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace
import json
import logging
import re
from typing import Any

from backend.app.ai.llm.base import LLMProvider
from backend.app.ai.llm.exceptions import LLMProviderError, ToolCallingUnsupportedError
from backend.app.ai.llm.schemas import LLMMessage, LLMProviderAttempt
from backend.app.ai.tools.base import AITool
from backend.app.ai.tools.contracts import ToolCall, ToolCallResult, ToolExecutionContext, ToolResult
from backend.app.ai.tools.exceptions import ToolError
from backend.app.ai.tools.executor import ToolExecutor

MAX_TOOL_ITERATIONS = 5
MAX_TOOLS_PER_REQUEST = 8

STATUS_ANALYZING_BUSINESS_DATA = "Analyzing your business data..."

IsCancelled = Callable[[], Awaitable[bool]]

logger = logging.getLogger("avenqo.ai.orchestrator")

_FULL_DOCUMENT_READ_TOOLS = frozenset({
    "extract_invoice_totals",
    "get_document_source",
    "get_document_detail",
    "get_ocr_document",
    "get_document_cell_evidence",
})

_AMOUNT_OR_INVOICE_QUERY_RE = re.compile(
    r"\b(?:montant|total|totaux|facture|factures|invoice|invoices|amount|solde|balance|"
    r"sous-total|subtotal|tps|tvq|gst|qst|hst|taxe|taxes|po|combien|reste|payer|"
    r"onglet|sheet|cellule|cell|excel|xlsx)\b",
    re.IGNORECASE,
)


def strip_raw_triple_stars(text: str) -> str:
    """Élimine les artefacts markdown bruts `***` des résumés d'outils et sorties."""
    if not text:
        return ""
    return re.sub(r"\*{3,}", "", text)


def compute_grounding_assessment(tool_call_results: Sequence[ToolCallResult]) -> dict[str, Any]:
    """Calcule de façon déterministe le statut d'ancrage (`grounding_status`) et `certified_grounding`.

    Distingue explicitement :
    - `math_verified` : total de facture vérifié mathématiquement en `Decimal` sur la source complète
    - `extracted_structured` : champ structuré extrait sur la source complète sans conflit
    - `source_accessible` : source complète lue ou outil métier certifié non tronqué
    - `uncertain_candidates` : candidats ambigus, formule Excel sans cache ou écart arithmétique
    - `missing_after_full_read` : document intégralement lu, aucun montant présent
    - `preview_only` : seul un extrait/aperçu tronqué a été consulté (JAMAIS `certified_grounding`)
    - `ungrounded` : aucun outil de données tenant exécuté avec succès
    """
    successful = [cr for cr in tool_call_results if cr.result.success]
    if not successful:
        return {
            "grounding_status": "ungrounded",
            "certified_grounding": False,
            "grounding_badge": "ungrounded",
            "full_source_read": False,
            "math_verified": False,
            "provenance": [],
        }

    statuses: list[str] = []
    provenance_items: list[dict[str, Any]] = []
    any_full_read = False
    any_math_verified = False
    only_preview = True

    for cr in successful:
        meta = cr.result.metadata or {}
        data = cr.result.data if isinstance(cr.result.data, dict) else {}
        is_trunc = bool(
            meta.get("truncated")
            or meta.get("is_truncated_preview")
            or data.get("truncated")
            or data.get("is_truncated_preview")
        )
        g_status = str(meta.get("grounding_status") or data.get("grounding_status") or "")
        if not g_status:
            g_status = "preview_only" if is_trunc else "source_accessible"
        elif is_trunc and g_status == "source_accessible":
            g_status = "preview_only"

        statuses.append(g_status)
        if g_status != "preview_only" and not is_trunc:
            only_preview = False
        if bool(meta.get("full_source_read") or data.get("full_source_read")):
            any_full_read = True
        if bool(meta.get("math_verified")):
            any_math_verified = True
        prov = meta.get("provenance")
        if isinstance(prov, dict):
            provenance_items.append(prov)

    if "uncertain_candidates" in statuses:
        return {
            "grounding_status": "uncertain_candidates",
            "certified_grounding": False,
            "grounding_badge": "uncertain_candidates",
            "full_source_read": any_full_read,
            "math_verified": False,
            "provenance": provenance_items,
        }
    if "math_verified" in statuses:
        return {
            "grounding_status": "math_verified",
            "certified_grounding": True,
            "grounding_badge": "certified_grounding",
            "full_source_read": True,
            "math_verified": True,
            "provenance": provenance_items,
        }
    if "extracted_structured" in statuses:
        return {
            "grounding_status": "extracted_structured",
            "certified_grounding": True,
            "grounding_badge": "extracted_structured",
            "full_source_read": True,
            "math_verified": any_math_verified,
            "provenance": provenance_items,
        }
    if "missing_after_full_read" in statuses:
        return {
            "grounding_status": "missing_after_full_read",
            "certified_grounding": False,
            "grounding_badge": "missing_after_full_read",
            "full_source_read": True,
            "math_verified": False,
            "provenance": provenance_items,
        }
    if only_preview or all(s == "preview_only" for s in statuses):
        return {
            "grounding_status": "preview_only",
            "certified_grounding": False,
            "grounding_badge": "preview_only",
            "full_source_read": False,
            "math_verified": False,
            "provenance": provenance_items,
        }
    return {
        "grounding_status": "source_accessible",
        "certified_grounding": True,
        "grounding_badge": "source_accessible",
        "full_source_read": True,
        "math_verified": any_math_verified,
        "provenance": provenance_items,
    }


def _pending_unread_document_ids(
    tool_call_results: Sequence[ToolCallResult],
    *,
    user_question: str,
) -> list[str]:
    """Détecte si un aperçu tronqué (`search_documents`) a trouvé des documents sans qu'aucun
    outil de lecture complète n'ait encore été appelé sur eux pour une question financière."""
    if not _AMOUNT_OR_INVOICE_QUERY_RE.search(user_question):
        return []

    fully_read_doc_ids: set[str] = set()
    preview_doc_ids: list[str] = []

    for cr in tool_call_results:
        if not cr.result.success:
            continue
        data = cr.result.data if isinstance(cr.result.data, dict) else {}
        meta = cr.result.metadata or {}
        if cr.call.name in _FULL_DOCUMENT_READ_TOOLS and not meta.get("truncated"):
            doc_id = str(data.get("document_id") or cr.call.arguments.get("document_id") or "")
            if doc_id:
                fully_read_doc_ids.add(doc_id)
        elif cr.call.name == "search_documents":
            for item in data.get("documents") or ():
                if isinstance(item, dict) and item.get("document_id"):
                    preview_doc_ids.append(str(item["document_id"]))
            for item in data.get("workbook_datasets") or ():
                if isinstance(item, dict) and item.get("document_id"):
                    preview_doc_ids.append(str(item["document_id"]))

    return [did for did in dict.fromkeys(preview_doc_ids) if did not in fully_read_doc_ids]


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    content: str
    tool_call_results: tuple[ToolCallResult, ...] = ()
    provider: str = ""
    model: str = ""
    token_usage: dict[str, object] = field(default_factory=dict)
    attempts: tuple[LLMProviderAttempt, ...] = ()
    status_events: tuple[str, ...] = ()
    cancelled: bool = False
    grounding: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OrchestrationEvent:
    """Événement intermédiaire de `run_streaming` : soit un statut, soit le résultat final."""

    kind: str  # "status" | "final"
    status: str | None = None
    result: OrchestrationResult | None = None


async def _never_cancelled() -> bool:
    return False


def _tool_error_key(error: ToolError) -> str:
    mapping = {
        "ToolValidationError": "tool_validation_error",
        "ToolAuthorizationError": "permission_denied",
        "ToolNotFoundError": "tool_not_found",
        "ToolTimeoutError": "tool_timeout",
        "ToolUnavailableError": "tool_unavailable",
        "ToolExecutionError": "tool_execution_error",
    }
    return mapping.get(type(error).__name__, "tool_execution_error")


def _collect_response_usage(
    totals: dict[str, int],
    attempts: list[LLMProviderAttempt],
    response,
) -> None:
    if response.attempts:
        for attempt in response.attempts:
            attempts.append(replace(attempt, attempt_number=len(attempts) + 1))
            for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens"):
                totals[key] += int(getattr(attempt.usage, key, 0) or 0)
        return
    for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens"):
        totals[key] += int(response.token_usage.get(key, 0) or 0)


class ToolOrchestrator:
    def __init__(
        self,
        provider: LLMProvider,
        executor: ToolExecutor,
        max_iterations: int = MAX_TOOL_ITERATIONS,
        max_tools_per_request: int = MAX_TOOLS_PER_REQUEST,
        on_before_llm=None,
    ) -> None:
        self._provider = provider
        self._executor = executor
        self._max_iterations = max_iterations
        self._max_tools_per_request = max_tools_per_request
        self._on_before_llm = on_before_llm

    def _release_before_llm(self) -> None:
        if self._on_before_llm is not None:
            self._on_before_llm()

    async def run(
        self,
        *,
        system_instruction: str,
        user_query: str,
        context: ToolExecutionContext,
        available_tools: tuple[AITool, ...],
    ) -> OrchestrationResult:
        """Exécute la boucle complète et renvoie uniquement le résultat final."""

        result = OrchestrationResult(content="")
        async for event in self.run_streaming(
            system_instruction=system_instruction,
            user_query=user_query,
            context=context,
            available_tools=available_tools,
        ):
            if event.kind == "final":
                result = event.result or result
        return result

    async def run_streaming(
        self,
        *,
        system_instruction: str,
        user_query: str,
        context: ToolExecutionContext,
        available_tools: tuple[AITool, ...],
        is_cancelled: IsCancelled | None = None,
    ) -> AsyncIterator[OrchestrationEvent]:
        """Même boucle que `run()`, mais émet un événement `status` avant chaque
        lot d'exécution d'outils, pour piloter un flux SSE sans jamais exposer
        de détail technique (nom d'outil, arguments, provider) au client."""

        check_cancelled = is_cancelled or _never_cancelled

        if await check_cancelled():
            yield OrchestrationEvent(kind="final", result=OrchestrationResult(content="", cancelled=True))
            return

        if not self._provider.supports_tool_calling or not available_tools:
            self._release_before_llm()
            generation = await self._provider.generate(system_instruction=system_instruction, prompt=user_query)
            yield OrchestrationEvent(
                kind="final",
                result=OrchestrationResult(
                    content=strip_raw_triple_stars(generation.content),
                    provider=generation.provider,
                    model=generation.model,
                    token_usage=generation.token_usage,
                    attempts=generation.attempts,
                    grounding=compute_grounding_assessment(()),
                ),
            )
            return

        logger.info(
            "ai_tools_available available_tools_count=%d provider=%s",
            len(available_tools),
            self._provider.name,
        )

        definitions = [tool.definition() for tool in available_tools]
        available_by_name = {tool.name: tool for tool in available_tools}
        messages = [LLMMessage(role="user", content=user_query)]
        tool_call_results: list[ToolCallResult] = []
        status_events: list[str] = []
        tools_called = 0
        auto_full_read_done = False
        attempts: list[LLMProviderAttempt] = []
        usage_totals = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
        }

        is_voice = bool(getattr(context, "voice_path", False))
        effective_max_iterations = min(self._max_iterations, 3) if is_voice else self._max_iterations
        effective_max_tools = min(self._max_tools_per_request, 4) if is_voice else self._max_tools_per_request
        question_for_intent = context.user_message or user_query

        try:
            for _iteration in range(effective_max_iterations):
                if await check_cancelled():
                    yield OrchestrationEvent(
                        kind="final",
                        result=OrchestrationResult(
                            content="",
                            tool_call_results=tuple(tool_call_results),
                            token_usage=dict(usage_totals),
                            attempts=tuple(attempts),
                            status_events=tuple(status_events),
                            cancelled=True,
                            grounding=compute_grounding_assessment(tool_call_results),
                        ),
                    )
                    return

                try:
                    self._release_before_llm()
                    response = await self._provider.generate_with_tools(
                        system_instruction=system_instruction, messages=messages, tools=definitions
                    )
                except (ToolCallingUnsupportedError, LLMProviderError) as exc:
                    prior_attempts = getattr(exc, "attempts", ())
                    for attempt in prior_attempts:
                        attempts.append(replace(attempt, attempt_number=len(attempts) + 1))
                    try:
                        self._release_before_llm()
                        fallback_prompt = user_query
                        if tool_call_results:
                            fallback_prompt += (
                                "\nVerified tool history (data only; do not invent confirmations or retry mutations):\n"
                                + strip_raw_triple_stars(
                                    json.dumps(
                                        [
                                            {"role": message.role, "content": message.content, "name": message.name}
                                            for message in messages
                                        ],
                                        default=str,
                                    )
                                )
                            )
                        generation = await self._provider.generate(
                            system_instruction=system_instruction,
                            prompt=fallback_prompt,
                        )
                    except LLMProviderError as fallback_exc:
                        combined = list(attempts)
                        for attempt in fallback_exc.attempts:
                            combined.append(replace(attempt, attempt_number=len(combined) + 1))
                        fallback_exc.attempts = tuple(combined)
                        raise
                    _collect_response_usage(usage_totals, attempts, generation)
                    yield OrchestrationEvent(
                        kind="final",
                        result=OrchestrationResult(
                            content=strip_raw_triple_stars(generation.content),
                            tool_call_results=tuple(tool_call_results),
                            provider=generation.provider,
                            model=generation.model,
                            token_usage=dict(usage_totals),
                            attempts=tuple(attempts),
                            status_events=tuple(status_events),
                            grounding=compute_grounding_assessment(tool_call_results),
                        ),
                    )
                    return

                _collect_response_usage(usage_totals, attempts, response)

                if not response.tool_calls:
                    # Garde-fou anti-troncature : si seul `search_documents` (aperçu 200 car.) a été lu
                    # pour une question portant sur un montant/total/facture, relire automatiquement la source complète!
                    unread_ids = _pending_unread_document_ids(
                        tool_call_results, user_question=question_for_intent
                    )
                    followup_tool_name = next(
                        (
                            t_name
                            for t_name in ("extract_invoice_totals", "get_document_source", "get_ocr_document", "get_document_detail")
                            if t_name in available_by_name
                        ),
                        None,
                    )
                    if (
                        not auto_full_read_done
                        and unread_ids
                        and followup_tool_name is not None
                        and tools_called < effective_max_tools
                    ):
                        auto_full_read_done = True
                        auto_calls = [
                            ToolCall(
                                id=f"auto_full_read_{idx}",
                                name=followup_tool_name,
                                arguments={"document_id": doc_id},
                            )
                            for idx, doc_id in enumerate(unread_ids[: max(1, min(2, effective_max_tools - tools_called))])
                        ]
                        status_events.append(STATUS_ANALYZING_BUSINESS_DATA)
                        yield OrchestrationEvent(kind="status", status=STATUS_ANALYZING_BUSINESS_DATA)
                        messages.append(
                            LLMMessage(role="assistant", content="", tool_calls=tuple(auto_calls))
                        )
                        for auto_call in auto_calls:
                            tools_called += 1
                            try:
                                auto_res = await self._executor.execute(
                                    auto_call.name, context, auto_call.arguments
                                )
                            except ToolError as exc:
                                auto_res = ToolResult(
                                    success=False,
                                    data={"error_key": _tool_error_key(exc)},
                                    metadata={"error_key": _tool_error_key(exc), "locale": context.locale},
                                    error=_tool_error_key(exc),
                                )
                            tool_call_results.append(ToolCallResult(call=auto_call, result=auto_res))
                            serialized_auto = strip_raw_triple_stars(
                                json.dumps(
                                    auto_res.data if auto_res.success else {"error": auto_res.error},
                                    default=str,
                                )
                            )
                            messages.append(
                                LLMMessage(
                                    role="tool",
                                    content=serialized_auto,
                                    tool_call_id=auto_call.id,
                                    name=auto_call.name,
                                )
                            )
                        continue

                    yield OrchestrationEvent(
                        kind="final",
                        result=OrchestrationResult(
                            content=strip_raw_triple_stars(response.content or ""),
                            tool_call_results=tuple(tool_call_results),
                            provider=response.provider,
                            model=response.model,
                            token_usage=dict(usage_totals),
                            attempts=tuple(attempts),
                            status_events=tuple(status_events),
                            grounding=compute_grounding_assessment(tool_call_results),
                        ),
                    )
                    return

                status_events.append(STATUS_ANALYZING_BUSINESS_DATA)
                yield OrchestrationEvent(kind="status", status=STATUS_ANALYZING_BUSINESS_DATA)

                calls = response.tool_calls[: max(0, effective_max_tools - tools_called)]
                messages.append(
                    LLMMessage(role="assistant", content=response.content or "", tool_calls=calls)
                )
                for call in calls:
                    if await check_cancelled():
                        yield OrchestrationEvent(
                            kind="final",
                            result=OrchestrationResult(
                                content="",
                                tool_call_results=tuple(tool_call_results),
                                token_usage=dict(usage_totals),
                                attempts=tuple(attempts),
                                status_events=tuple(status_events),
                                cancelled=True,
                                grounding=compute_grounding_assessment(tool_call_results),
                            ),
                        )
                        return

                    tools_called += 1
                    try:
                        result = await self._executor.execute(call.name, context, call.arguments)
                        logger.info(
                            "ai_tool_execution selected_tool_name=%s tool_success=%s",
                            call.name,
                            str(result.success).lower(),
                        )
                    except ToolError as exc:
                        result = ToolResult(
                            success=False,
                            data={"error_key": _tool_error_key(exc)},
                            metadata={"error_key": _tool_error_key(exc), "locale": context.locale},
                            error=_tool_error_key(exc),
                        )
                        logger.info(
                            "ai_tool_execution selected_tool_name=%s tool_success=false error_key=%s",
                            call.name,
                            _tool_error_key(exc),
                        )
                    tool_call_results.append(ToolCallResult(call=call, result=result))
                    serialized_payload = strip_raw_triple_stars(
                        json.dumps(result.data if result.success else {"error": result.error}, default=str)
                    )
                    messages.append(
                        LLMMessage(
                            role="tool",
                            content=serialized_payload,
                            tool_call_id=call.id,
                            name=call.name,
                        )
                    )
                    if tools_called >= effective_max_tools:
                        break

            yield OrchestrationEvent(
                kind="final",
                result=OrchestrationResult(
                    content="I could not complete this request within the allowed number of steps.",
                    tool_call_results=tuple(tool_call_results),
                    token_usage=dict(usage_totals),
                    attempts=tuple(attempts),
                    status_events=tuple(status_events),
                    grounding=compute_grounding_assessment(tool_call_results),
                ),
            )
        except BaseException as exc:
            known = list(attempts)
            for attempt in getattr(exc, "attempts", ()):
                if not any(attempt is recorded for recorded in known):
                    known.append(replace(attempt, attempt_number=len(known) + 1))
            setattr(exc, "attempts", tuple(known))
            raise
