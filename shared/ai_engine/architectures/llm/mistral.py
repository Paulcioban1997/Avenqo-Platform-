"""Candidat Mistral (sera implémenté avec un modèle open-weights Mistral via transformers)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class MistralModel(UntrainedModel):
    candidate_id = "mistral"
