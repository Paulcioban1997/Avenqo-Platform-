"""Catalogue des modèles Vision : entièrement réutilisé depuis `architectures/vision`,
unique source de vérité (aucun modèle propre à cette famille).
"""

from shared.ai_engine.architectures.vision.cnn import CNNModel
from shared.ai_engine.architectures.vision.efficientnet import EfficientNetModel
from shared.ai_engine.architectures.vision.resnet import ResNetModel
from shared.ai_engine.architectures.vision.vision_transformer import VisionTransformerModel
from shared.ai_engine.core.model_candidate_registry import ModelCandidateRegistry


def build_vision_registry() -> ModelCandidateRegistry:
    registry = ModelCandidateRegistry()
    registry.register("cnn", CNNModel)
    registry.register("resnet", ResNetModel)
    registry.register("efficientnet", EfficientNetModel)
    registry.register("vision_transformer", VisionTransformerModel)
    return registry
