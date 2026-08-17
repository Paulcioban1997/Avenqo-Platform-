"""Candidat factorisation matricielle (sera implémenté avec surprise.SVD ou équivalent)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class MatrixFactorizationModel(UntrainedModel):
    candidate_id = "matrix_factorization"
