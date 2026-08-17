"""Candidat CatBoost (sera implémenté avec catboost.CatBoostClassifier/CatBoostRegressor)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class CatBoostModel(UntrainedModel):
    candidate_id = "catboost"
