"""Candidat Temporal Fusion Transformer (sera implémenté avec pytorch-forecasting.TemporalFusionTransformer)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class TFTModel(UntrainedModel):
    candidate_id = "tft"
