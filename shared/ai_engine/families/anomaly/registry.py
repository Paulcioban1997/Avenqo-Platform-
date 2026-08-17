"""Catalogue des modèles Anomaly Detection : combine l'AutoEncoder partagé (réutilisé
depuis `architectures/deep_learning`) et Isolation Forest, propre à cette famille.
"""

from shared.ai_engine.architectures.deep_learning.autoencoder import AutoencoderModel
from shared.ai_engine.core.model_candidate_registry import ModelCandidateRegistry
from shared.ai_engine.families.anomaly.models.isolation_forest import IsolationForestModel


def build_anomaly_registry() -> ModelCandidateRegistry:
    registry = ModelCandidateRegistry()
    registry.register("isolation_forest", IsolationForestModel)
    registry.register("autoencoder", AutoencoderModel)
    return registry
