"""Catégorie technique Deep Learning : réseaux de neurones génériques (unique source
de vérité, sans copie dans families/). Sert aussi de domaine d'exécution par défaut
pour les tâches neuronales génériques de l'AIEngine.
"""

from shared.ai_engine.architectures.deep_learning.keras_dense_builder import build_dense_network
from shared.ai_engine.architectures.deep_learning.strategy import DeepLearningStrategy

__all__ = ["DeepLearningStrategy", "build_dense_network"]
