"""Candidat BERT (sera implémenté avec transformers.AutoModelForSequenceClassification)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class BertClassifierModel(UntrainedModel):
    candidate_id = "bert_classifier"
