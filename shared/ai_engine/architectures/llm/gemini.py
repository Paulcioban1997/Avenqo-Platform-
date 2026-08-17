"""Candidat Gemini (sera implémenté avec l'API Google Gemini)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class GeminiModel(UntrainedModel):
    candidate_id = "gemini"
