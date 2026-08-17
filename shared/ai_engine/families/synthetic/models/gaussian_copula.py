"""Candidat Gaussian Copula (sera implémenté avec sdv.single_table.GaussianCopulaSynthesizer)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class GaussianCopulaModel(UntrainedModel):
    candidate_id = "gaussian_copula"
