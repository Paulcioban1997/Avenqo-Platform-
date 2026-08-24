"""Retrieval (RAG) du Support AI Avenqo (Phase 32) — strictement scopé à la
documentation produit. NE PREND JAMAIS `tenant_id`/`company_id` en paramètre
et NE REQUÊTE JAMAIS `Dataset` ni aucune table métier — contrairement à
`backend/app/ai/chat/retrieval_service.py` (Phase 28).
"""

from __future__ import annotations

import re

from backend.app.ai.chat.source_service import RetrievedSource
from backend.app.ai.support.knowledge_base import get_documents

_WORD_RE = re.compile(r"[a-zA-Z0-9]+")


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in _WORD_RE.findall(text)}


class PlatformKnowledgeRetrievalService:
    def __init__(self, knowledge_root: str) -> None:
        self._root = knowledge_root

    def retrieve_context(self, query: str, limit: int = 4) -> list[RetrievedSource]:
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        scored: list[tuple[int, object]] = []
        for document in get_documents(self._root):
            doc_tokens = _tokenize(document.title) | _tokenize(document.content) | {tag.lower() for tag in document.tags}
            score = len(query_tokens & doc_tokens)
            if score > 0:
                scored.append((score, document))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            RetrievedSource(
                source_type="platform_doc",
                identifier=document.id,
                name=document.title,
                content=document.content,
                metadata={"path": document.path, "tags": list(document.tags)},
            )
            for _, document in scored[:limit]
        ]
