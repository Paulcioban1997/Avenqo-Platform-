"""Candidat Claude (sera implémenté avec l'API Anthropic Claude)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class ClaudeModel(UntrainedModel):
    candidate_id = "claude"
