"""Candidat LightGBM (sera implémenté avec lightgbm.LGBMClassifier/LGBMRegressor)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class LightGBMModel(UntrainedModel):
    candidate_id = "lightgbm"
