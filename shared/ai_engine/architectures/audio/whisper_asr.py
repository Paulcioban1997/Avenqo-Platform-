"""Candidat Whisper (sera implémenté avec transformers.WhisperForConditionalGeneration)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class WhisperASRModel(UntrainedModel):
    candidate_id = "whisper_asr"
