"""Enterprise Memory tools for Central AI orchestration (Phase 8.1).

Enables Central AI to store and recall authorized company and user preferences
across conversations while strictly maintaining tenant boundaries.
"""

from __future__ import annotations

from typing import Any
from pydantic import Field
from sqlalchemy.orm import Session

from backend.app.ai.tools.base import MemoryAITool, ToolArguments
from backend.app.ai.tools.contracts import ToolExecutionContext, ToolResult
from backend.app.ai.memory.service import AvenqoMemoryService
from backend.app.models.ai_memory import MemoryScope, MemoryType


class SaveEnterpriseMemoryArgs(ToolArguments):
    content: str = Field(min_length=3, description="Information, consigne ou préférence à mémoriser (ex: 'L'entreprise privilégie les livraisons express pour les VIP').")
    scope: str = Field(default="company", description="Portée de la mémoire : 'company' (partagée par l'équipe) ou 'user' (privée à l'utilisateur).")
    memory_type: str = Field(default="preference", description="Type : 'preference', 'context', 'instruction', 'fact'.")


class SearchEnterpriseMemoryArgs(ToolArguments):
    query: str = Field(min_length=2, description="Terme ou sujet de recherche dans les mémoires de l'entreprise.")
    scope: str | None = Field(default=None, description="Filtrer par portée ('company' ou 'user') ou laisser vide pour tout.")


class SaveEnterpriseMemoryTool(MemoryAITool):
    name = "save_enterprise_memory"
    description = (
        "Enregistre une préférence, instruction ou fait clé dans la mémoire d'entreprise persistante (Mem0 / Avenqo Memory). "
        "Les données sont strictement isolées par tenant et réutilisables lors des futures interactions."
    )
    input_schema = SaveEnterpriseMemoryArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: SaveEnterpriseMemoryArgs) -> ToolResult:
        service = AvenqoMemoryService(self._session)
        scope_enum = MemoryScope.COMPANY if arguments.scope.lower() == "company" else MemoryScope.USER
        mem_type_enum = MemoryType(arguments.memory_type.lower()) if arguments.memory_type.lower() in [m.value for m in MemoryType] else MemoryType.FACT

        record = service.add_memory(
            tenant_id=context.tenant.company_id,
            user_id=context.tenant.user_id,
            content=arguments.content,
            scope=scope_enum,
            memory_type=mem_type_enum,
            source_module="central_ai",
        )

        scope_val = getattr(record, "memory_scope", arguments.scope)
        type_val = getattr(record, "memory_type", arguments.memory_type)
        if hasattr(scope_val, "value"):
            scope_val = scope_val.value
        if hasattr(type_val, "value"):
            type_val = type_val.value

        return ToolResult(
            success=True,
            data={
                "memory_id": str(record.id),
                "scope": str(scope_val),
                "memory_type": str(type_val),
                "content": record.content,
                "message": "Préférence d'entreprise enregistrée avec succès dans la mémoire persistante.",
            },
            source_refs=("ai_enterprise_memories",),
        )


class SearchEnterpriseMemoryTool(MemoryAITool):
    name = "search_enterprise_memory"
    description = (
        "Recherche dans la mémoire persistante de l'entreprise des préférences ou faits enregistrés précédemment. "
        "Ne renvoie JAMAIS de mémoires appartenant à d'autres entreprises (isolation stricte)."
    )
    input_schema = SearchEnterpriseMemoryArgs
    required_permissions = ("ai:use",)

    def __init__(self, session: Session) -> None:
        self._session = session

    async def run(self, context: ToolExecutionContext, arguments: SearchEnterpriseMemoryArgs) -> ToolResult:
        service = AvenqoMemoryService(self._session)
        scope_enum = None
        if arguments.scope:
            scope_enum = MemoryScope.COMPANY if arguments.scope.lower() == "company" else MemoryScope.USER

        records = service.search_memories(
            tenant_id=context.tenant.company_id,
            user_id=context.tenant.user_id,
            query=arguments.query,
            scope=scope_enum,
            limit=5,
        )

        results = [
            {
                "id": str(r.id),
                "scope": str(getattr(r, "memory_scope", "")),
                "type": str(getattr(r, "memory_type", "")),
                "content": r.content,
                "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
            }
            for r in records
        ]

        return ToolResult(
            success=True,
            data={
                "results_count": len(results),
                "memories": results,
            },
            source_refs=("ai_enterprise_memories",),
        )
