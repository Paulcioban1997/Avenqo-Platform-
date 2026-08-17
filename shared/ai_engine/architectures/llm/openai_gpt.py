"""Candidat GPT hébergé (sera implémenté avec l'API OpenAI, fine-tuning/prompting managé)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class OpenAIGPTModel(UntrainedModel):
    candidate_id = "openai_gpt"
