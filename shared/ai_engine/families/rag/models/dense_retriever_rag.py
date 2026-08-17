"""Candidat RAG à récupération dense (sera implémenté avec un retriever d'embeddings + un LLM)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class DenseRetrieverRAGModel(UntrainedModel):
    candidate_id = "dense_retriever_rag"
