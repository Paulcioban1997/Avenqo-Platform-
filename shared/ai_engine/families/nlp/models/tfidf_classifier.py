"""Candidat TF-IDF + classifieur linéaire (sera implémenté avec sklearn.feature_extraction.text.TfidfVectorizer)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class TfidfClassifierModel(UntrainedModel):
    candidate_id = "tfidf_classifier"
