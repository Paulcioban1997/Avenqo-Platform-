import json
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.ai.chat.exceptions import RetrievalError
from backend.app.ai.chat.source_service import RetrievedSource
from shared.ai_engine.contracts import TenantContext


def _factual_evidence(value):
    """Keep structured facts, excluding extractor-generated narrative templates."""
    if isinstance(value, dict):
        return {key: _factual_evidence(item) for key, item in value.items() if not key.startswith("direct_statement")}
    if isinstance(value, list):
        return [_factual_evidence(item) for item in value]
    return value


class RetrievalService:
    """Fresh document evidence restricted to the authenticated user's selection."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def retrieve_context(self, tenant_id: UUID, query: str, limit: int = 5, *, user_id: UUID | None = None) -> list[RetrievedSource]:
        if user_id is None:
            return []
        from backend.app.services.selected_document_evidence import inspect_selected_documents

        try:
            payload = inspect_selected_documents(self._db, TenantContext(tenant_id, user_id))
        except Exception as exc:
            raise RetrievalError("Selected source evidence unavailable") from exc
        return [
            RetrievedSource(
                "dataset", item["dataset_id"], item["name"],
                json.dumps(_factual_evidence(item), ensure_ascii=False, default=str),
                {"dataset_id": item["dataset_id"], "status": item["status"], "selected": True},
            )
            for item in payload["documents"][:max(0, limit)]
        ]
