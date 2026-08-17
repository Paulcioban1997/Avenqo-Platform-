"""Candidat RAG hybride (sera implémenté avec une recherche dense + lexicale combinée type BM25 + embeddings)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class HybridRAGModel(UntrainedModel):
    candidate_id = "hybrid_rag"
