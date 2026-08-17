"""Catalogue des modèles RAG pré-intégrés (disponibles, pas encore entraînés)."""

from shared.ai_engine.core.model_candidate_registry import ModelCandidateRegistry
from shared.ai_engine.families.rag.models.dense_retriever_rag import DenseRetrieverRAGModel
from shared.ai_engine.families.rag.models.hybrid_rag import HybridRAGModel


def build_rag_registry() -> ModelCandidateRegistry:
    registry = ModelCandidateRegistry()
    registry.register("dense_retriever_rag", DenseRetrieverRAGModel)
    registry.register("hybrid_rag", HybridRAGModel)
    return registry
