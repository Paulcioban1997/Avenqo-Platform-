from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai.chat.exceptions import RetrievalError
from backend.app.ai.chat.source_service import RetrievedSource
from backend.app.models import Dataset


class RetrievalService:
    """First RAG adapter: metadata only, always constrained to one tenant."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def retrieve_context(self, tenant_id: UUID, query: str, limit: int = 5) -> list[RetrievedSource]:
        try:
            items = self._db.scalars(select(Dataset).where(Dataset.company_id == tenant_id).order_by(Dataset.uploaded_at.desc()).limit(limit)).all()
        except Exception as exc:
            raise RetrievalError("Impossible de récupérer le contexte de l'entreprise") from exc
        return [RetrievedSource("dataset", str(item.id), item.name, f"Dataset: {item.name}; type: {item.type}; lignes: {item.rows_count}; colonnes: {item.columns_count}.", {"dataset_id": str(item.id), "type": item.type, "rows_count": item.rows_count, "columns_count": item.columns_count}) for item in items]