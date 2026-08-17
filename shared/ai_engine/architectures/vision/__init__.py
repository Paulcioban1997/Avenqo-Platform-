"""Catalogue Vision : architectures de traitement d'image, réutilisées par la famille Vision
et par toute autre famille métier ayant besoin d'un modèle image (unique source de vérité).
"""

from shared.ai_engine.architectures.vision.cnn import CNNModel
from shared.ai_engine.architectures.vision.efficientnet import EfficientNetModel
from shared.ai_engine.architectures.vision.resnet import ResNetModel
from shared.ai_engine.architectures.vision.vision_transformer import VisionTransformerModel

__all__ = ["CNNModel", "ResNetModel", "EfficientNetModel", "VisionTransformerModel"]
