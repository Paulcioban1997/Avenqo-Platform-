"""Candidat N-BEATS (sera implémenté avec pytorch-forecasting.NBeats)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class NBeatsModel(UntrainedModel):
    candidate_id = "nbeats"
