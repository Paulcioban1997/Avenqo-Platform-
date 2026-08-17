"""Candidat Llama (sera implémenté avec un modèle open-weights Meta Llama via transformers)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class LlamaModel(UntrainedModel):
    candidate_id = "llama"
