"""Catalogue des modèles Synthetic Data : combine les architectures génératives partagées
(GAN, CTGAN, TVAE, réutilisées depuis `architectures/deep_learning`) et Gaussian Copula,
propre à cette famille.
"""

from shared.ai_engine.architectures.deep_learning.ctgan import CTGANModel
from shared.ai_engine.architectures.deep_learning.gan import GANModel
from shared.ai_engine.architectures.deep_learning.tvae import TVAEModel
from shared.ai_engine.core.model_candidate_registry import ModelCandidateRegistry
from shared.ai_engine.families.synthetic.models.gaussian_copula import GaussianCopulaModel


def build_synthetic_registry() -> ModelCandidateRegistry:
    registry = ModelCandidateRegistry()
    registry.register("gaussian_copula", GaussianCopulaModel)
    registry.register("gan", GANModel)
    registry.register("ctgan", CTGANModel)
    registry.register("tvae", TVAEModel)
    return registry
