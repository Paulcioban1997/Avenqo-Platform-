"""Candidat AdaBoost (sera implémenté avec sklearn.ensemble.AdaBoostClassifier/Regressor)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class AdaBoostModel(UntrainedModel):
    candidate_id = "adaboost"
