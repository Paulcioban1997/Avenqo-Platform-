"""Entraînement des candidats RAG : identique à toutes les familles."""

from shared.ai_engine.core.trainer import Trainer


class RAGTrainer(Trainer):
    """Point d'extension si l'entraînement RAG nécessite un jour une indexation vectorielle dédiée."""
