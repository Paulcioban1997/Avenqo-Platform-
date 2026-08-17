"""Candidat filtrage collaboratif (sera implémenté avec une factorisation implicite type ALS)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class CollaborativeFilteringModel(UntrainedModel):
    candidate_id = "collaborative_filtering"
