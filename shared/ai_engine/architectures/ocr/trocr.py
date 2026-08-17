"""Candidat TrOCR (sera implémenté avec transformers.VisionEncoderDecoderModel)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class TrOCRModel(UntrainedModel):
    candidate_id = "trocr"
