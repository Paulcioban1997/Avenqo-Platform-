"""Entraînement des candidats LLM : identique à toutes les familles."""

from shared.ai_engine.core.trainer import Trainer


class LLMTrainer(Trainer):
    """Point d'extension si l'entraînement LLM nécessite un jour un fine-tuning LoRA dédié."""
