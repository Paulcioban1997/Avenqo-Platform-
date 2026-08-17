"""Candidat ResNet (sera implémenté avec keras.applications.ResNet50 / blocs résiduels)."""

from shared.ai_engine.core.model_stub import UntrainedModel


class ResNetModel(UntrainedModel):
    candidate_id = "resnet"
