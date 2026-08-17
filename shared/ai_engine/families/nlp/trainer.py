"""Entraînement des candidats NLP : identique à toutes les familles."""

from shared.ai_engine.core.trainer import Trainer


class NLPTrainer(Trainer):
    """Point d'extension si l'entraînement NLP nécessite un jour une tokenisation dédiée."""
