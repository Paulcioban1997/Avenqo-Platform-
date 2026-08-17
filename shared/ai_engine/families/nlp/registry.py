"""Catalogue des modèles NLP pré-intégrés (disponibles, pas encore entraînés)."""

from shared.ai_engine.core.model_candidate_registry import ModelCandidateRegistry
from shared.ai_engine.families.nlp.models.bert_classifier import BertClassifierModel
from shared.ai_engine.families.nlp.models.tfidf_classifier import TfidfClassifierModel


def build_nlp_registry() -> ModelCandidateRegistry:
    registry = ModelCandidateRegistry()
    registry.register("tfidf_classifier", TfidfClassifierModel)
    registry.register("bert_classifier", BertClassifierModel)
    return registry
